"""The Dashboard analytics summary aggregates jobs, the funnel, and AI cost.

Rows are seeded straight through the ORM on the test's rolled-back session (the
same session the endpoint reads), then the aggregates are asserted over the HTTP
API. Covers the empty database (all zeros), each section's grouping, and the
trailing-window parameter for the AI daily series.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import AiRun, Application, ApplicationStatus, Job


def _seed(db):
    """Seed a fixed scenario and return timing anchors for date assertions.

    Jobs (5): manual×2, upwork×2, capture×1 — with a spread of match scores and
    part-time flags. Applications (4): one per stage except ``offer``. AI runs
    (4): three inside a 30-day window, one 40 days old (outside it).
    """
    now = datetime.now(timezone.utc)
    day1, day2, day40 = (now - timedelta(days=n) for n in (1, 2, 40))

    def job(source, score=None, ptf=None, n=[0]):
        n[0] += 1
        return Job(
            source=source,
            url=f"https://example.test/jobs/{source}-{n[0]}",
            title=f"{source} gig {n[0]}",
            workload="part_time",
            match_score=score,
            match_part_time_fit=ptf,
        )

    j_high = job("manual", score=85, ptf=True)  # high band, part-time fit
    j_unscored = job("manual")  # not scored
    j_mid = job("upwork", score=50, ptf=True)  # medium band, part-time fit
    j_low = job("capture", score=20, ptf=False)  # low band
    j_high2 = job("upwork", score=95)  # high band, ptf unknown

    # Applications: one per stage except 'offer'; j_high2 stays untracked.
    db.add_all(
        [
            Application(job=j_high, status=ApplicationStatus.applied),
            Application(job=j_unscored, status=ApplicationStatus.saved),
            Application(job=j_mid, status=ApplicationStatus.interviewing),
            Application(job=j_low, status=ApplicationStatus.rejected),
        ]
    )

    db.add_all(
        [
            AiRun(feature="score_match", model="m", status="success",
                  input_tokens=100, output_tokens=50, cost_usd=0.01, created_at=day1),
            AiRun(feature="score_match", model="m", status="success",
                  input_tokens=200, output_tokens=80, cost_usd=0.02, created_at=day2),
            AiRun(feature="tailor_cv", model="m", status="success",
                  input_tokens=500, output_tokens=300, cost_usd=0.05, created_at=day1),
            AiRun(feature="draft_proposal", model="m", status="success",
                  input_tokens=300, output_tokens=150, cost_usd=0.03, created_at=day40),
        ]
    )
    db.add_all([j_high2])  # ensure the untracked job is persisted too
    db.flush()
    return {"day1": day1.date().isoformat(), "day2": day2.date().isoformat(),
            "day40": day40.date().isoformat()}


def test_empty_db_all_zeros(client) -> None:
    resp = client.get("/api/analytics/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["jobs"] == {
        "total": 0,
        "by_source": {"manual": 0, "capture": 0, "upwork": 0, "freelancer": 0},
    }
    assert body["match"] == {
        "scored": 0, "unscored": 0, "part_time_fit": 0,
        "bands": {"low": 0, "medium": 0, "high": 0},
    }
    assert body["pipeline"] == {
        "total": 0,
        "by_status": {"saved": 0, "applied": 0, "interviewing": 0, "offer": 0, "rejected": 0},
        "applied_conversion": 0.0,
    }
    assert body["ai"] == {
        "total_cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
        "by_feature": [], "days": 30, "recent": [],
    }


def test_jobs_by_source(client, db_session) -> None:
    _seed(db_session)
    jobs = client.get("/api/analytics/summary").json()["jobs"]
    assert jobs["total"] == 5
    assert jobs["by_source"] == {"manual": 2, "upwork": 2, "capture": 1, "freelancer": 0}


def test_match_distribution(client, db_session) -> None:
    _seed(db_session)
    match = client.get("/api/analytics/summary").json()["match"]
    assert match["scored"] == 4  # 85, 50, 20, 95
    assert match["unscored"] == 1
    assert match["bands"] == {"low": 1, "medium": 1, "high": 2}  # 20 / 50 / (85,95)
    assert match["part_time_fit"] == 2  # only the two flagged True


def test_pipeline_funnel_and_conversion(client, db_session) -> None:
    _seed(db_session)
    pipeline = client.get("/api/analytics/summary").json()["pipeline"]
    assert pipeline["total"] == 4
    assert pipeline["by_status"] == {
        "saved": 1, "applied": 1, "interviewing": 1, "offer": 0, "rejected": 1
    }
    # 3 of 4 cards moved past 'saved'.
    assert pipeline["applied_conversion"] == pytest.approx(0.75)


def test_ai_cost_totals_and_by_feature(client, db_session) -> None:
    _seed(db_session)
    ai = client.get("/api/analytics/summary").json()["ai"]

    assert ai["total_cost_usd"] == pytest.approx(0.11)  # 0.01+0.02+0.05+0.03
    assert ai["input_tokens"] == 1100
    assert ai["output_tokens"] == 580

    # Ordered by spend desc, ties broken by feature name.
    assert [f["feature"] for f in ai["by_feature"]] == [
        "tailor_cv", "draft_proposal", "score_match"
    ]
    by_feature = {f["feature"]: f for f in ai["by_feature"]}
    assert by_feature["score_match"]["runs"] == 2
    assert by_feature["score_match"]["cost_usd"] == pytest.approx(0.03)
    assert by_feature["score_match"]["input_tokens"] == 300
    assert by_feature["score_match"]["output_tokens"] == 130
    assert by_feature["tailor_cv"]["runs"] == 1


def test_ai_recent_daily_series(client, db_session) -> None:
    anchors = _seed(db_session)
    ai = client.get("/api/analytics/summary").json()["ai"]

    assert ai["days"] == 30
    # The 40-day-old run is outside the default window; two days remain, oldest first.
    recent = ai["recent"]
    assert [r["date"] for r in recent] == [anchors["day2"], anchors["day1"]]

    # day2: only the score_match run.
    assert recent[0] == {
        "date": anchors["day2"], "cost_usd": pytest.approx(0.02),
        "input_tokens": 200, "output_tokens": 80, "runs": 1,
    }
    # day1: score_match + tailor_cv collapse into one bucket.
    assert recent[1] == {
        "date": anchors["day1"], "cost_usd": pytest.approx(0.06),
        "input_tokens": 600, "output_tokens": 350, "runs": 2,
    }


def test_days_window_param_widens(client, db_session) -> None:
    anchors = _seed(db_session)
    ai = client.get("/api/analytics/summary", params={"days": 60}).json()["ai"]

    assert ai["days"] == 60
    # A 60-day window now reaches the 40-day-old run: three buckets, oldest first.
    assert [r["date"] for r in ai["recent"]] == [
        anchors["day40"], anchors["day2"], anchors["day1"]
    ]
    assert ai["recent"][0]["cost_usd"] == pytest.approx(0.03)  # the draft_proposal run


def test_days_param_is_bounded(client) -> None:
    assert client.get("/api/analytics/summary", params={"days": 0}).status_code == 422
    assert client.get("/api/analytics/summary", params={"days": 366}).status_code == 422
