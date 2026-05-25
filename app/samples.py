"""Sample questions per database + source links shown in the sidebar."""

from __future__ import annotations

SOURCE_LINKS: dict[str, tuple[str, str]] = {
    "chinook": (
        "Chinook SQLite (lerocha/chinook-database)",
        "https://github.com/lerocha/chinook-database",
    ),
    "_bird_default": (
        "BIRD Mini-Dev (bird-bench.github.io)",
        "https://bird-bench.github.io/",
    ),
}


def source_link_for(db_id: str) -> tuple[str, str] | None:
    if db_id in SOURCE_LINKS:
        return SOURCE_LINKS[db_id]
    if db_id.startswith("bird_"):
        return SOURCE_LINKS["_bird_default"]
    return None


SAMPLE_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "chinook": [
        ("simple", "How many albums are in the store?"),
        ("simple", "Which 5 artists have the most albums?"),
        ("moderate", "What is the total revenue per genre?"),
    ],
    "bird_california_schools": [
        (
            "simple",
            "How many schools with an average score in Math greater than 400 in the SAT test are exclusively virtual?",
        ),
        (
            "simple",
            "What is the average number of test takers from Fresno schools that opened between 1/1/1980 and 12/31/1980?",
        ),
        (
            "moderate",
            "What is the ratio of merged Unified School District schools in Orange County to merged Elementary School District schools?",
        ),
    ],
    "bird_card_games": [
        ("simple", "How many cards have infinite power?"),
        (
            "simple",
            "What language is the set of 180 cards that belongs to the Ravnica block translated into?",
        ),
        (
            "moderate",
            "Among the sets in the block 'Ice Age', how many of them have an Italian translation?",
        ),
    ],
    "bird_codebase_community": [
        ("simple", "When did 'chl' cast its first vote in a post?"),
        (
            "simple",
            "What is the display name of the user who acquired the first Autobiographer badge?",
        ),
        (
            "moderate",
            "Among the posts with views ranging from 100 to 150, what is the comment with the highest score?",
        ),
    ],
    "bird_debit_card_specializing": [
        ("simple", "What segment did the customer have at 2012/8/23 21:20:00?"),
        (
            "simple",
            "What is the percentage of 'premium' against the overall segment in Country = 'SVK'?",
        ),
        (
            "moderate",
            "What was the average monthly consumption of customers in SME for the year 2013?",
        ),
    ],
    "bird_european_football_2": [
        ("simple", "List down most tallest players' name."),
        ("simple", "Please name one player whose overall strength is the greatest."),
        ("moderate", "What was the overall rating for Aaron Mooy on 2016/2/4?"),
    ],
    "bird_financial": [
        (
            "simple",
            "For the female client who was born in 1976/1/29, which district did she opened her account?",
        ),
        (
            "simple",
            "List out the no. of districts that have female average salary is more than 6000 but less than 10000?",
        ),
        (
            "moderate",
            "Provide the IDs and age of the client with high level credit card, which is eligible for loans.",
        ),
    ],
    "bird_formula_1": [
        ("simple", "What's the reference name of Marina Bay Street Circuit?"),
        ("simple", "Please state the reference name of the oldest German driver."),
        ("simple", "What's Bruno Senna's Q1 result in the qualifying race No. 354?"),
    ],
    "bird_student_club": [
        ("simple", "What's Angela Sanders's major?"),
        ("simple", "Mention the total expense used on 8/20/2019."),
        ("simple", "What is the total amount of money spent for food?"),
    ],
    "bird_superhero": [
        ("simple", "What is Copycat's race?"),
        ("moderate", "Which hero was the fastest?"),
        ("moderate", "Who is the dumbest superhero?"),
    ],
    "bird_thrombosis_prediction": [
        ("simple", "How many female patients were given an APS diagnosis?"),
        ("moderate", "State the ID and age of patient with positive degree of coagulation."),
        ("moderate", "Was the patient with the number 57266's uric acid within a normal range?"),
    ],
    "bird_toxicology": [
        ("simple", "How many connections does the atom 19 have?"),
        ("moderate", "Which non-carcinogenic molecules consisted more than 5 atoms?"),
        ("challenging", "List the elements of all the triple bonds."),
    ],
}
