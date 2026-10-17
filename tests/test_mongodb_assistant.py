import pytest

from cricketstats.mongodb_assistant import deterministic_plan, parse_plan, validate_plan


COLLECTIONS = {"player_career_stats", "player_batting_innings_stats", "match_stats"}


def test_parse_and_validate_read_only_pipeline():
    plan = parse_plan('```json\n{"collection":"player_career_stats","pipeline":[{"$match":{"format_group":"Test"}}]}\n```')
    validate_plan(plan, COLLECTIONS)
    assert plan["pipeline"][-1] == {"$limit": 50}


@pytest.mark.parametrize("stage", ["$out", "$merge", "$documents"])
def test_blocks_write_or_unapproved_stages(stage):
    plan = {"collection": "match_stats", "pipeline": [{stage: "bad"}]}
    with pytest.raises(ValueError):
        validate_plan(plan, COLLECTIONS)


def test_blocks_javascript_operator_nested_in_match():
    plan = {"collection": "match_stats", "pipeline": [{"$match": {"$where": "true"}}]}
    with pytest.raises(ValueError):
        validate_plan(plan, COLLECTIONS)


def test_rejects_unknown_collection_and_lookup():
    with pytest.raises(ValueError):
        validate_plan({"collection": "secret", "pipeline": []}, COLLECTIONS)
    with pytest.raises(ValueError):
        validate_plan({"collection": "match_stats", "pipeline": [{"$lookup": {"from": "secret"}}]}, COLLECTIONS)


def test_rejects_large_limit():
    plan = {"collection": "match_stats", "pipeline": [{"$limit": 1000}]}
    with pytest.raises(ValueError):
        validate_plan(plan, COLLECTIONS)


def test_career_hundreds_use_authoritative_collection():
    plan = deterministic_plan("How many Test hundreds did Sachin Tendulkar score?", ["SR Tendulkar"])
    assert plan["collection"] == "player_career_stats"
    assert plan["pipeline"][0]["$match"]["player_name"] == "SR Tendulkar"
    assert plan["pipeline"][2]["$project"]["hundreds"] == 1


def test_opposition_hundreds_are_not_forced_to_career_total():
    assert deterministic_plan(
        "How many Test hundreds did Tendulkar score against Australia?", ["SR Tendulkar"]
    ) is None


def test_ipl_cap_question_uses_curated_collection():
    plan = deterministic_plan("Who won the IPL Orange Cap in 2023?", [])
    assert plan["collection"] == "orange_cap_winners"
    assert plan["pipeline"][0] == {"$match": {"year": 2023}}


def test_ipl_leader_question_uses_career_collection():
    plan = deterministic_plan("Who has scored the most IPL runs?", [])
    assert plan["collection"] == "player_career_stats"
    assert plan["pipeline"][1] == {"$sort": {"runs_scored": -1, "matches": -1}}


def test_first_indian_twin_centuries_uses_innings_data():
    plan = deterministic_plan(
        "Who was the first Indian to score centuries in both innings of a Test?", []
    )
    assert plan["collection"] == "player_batting_innings_stats"
    assert plan["pipeline"][0]["$match"]["runs_scored"] == {"$gte": 100}
    assert plan["pipeline"][3] == {"$sort": {"match_date": 1}}
