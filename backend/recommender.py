"""Small, interpretable *prototype* model-based MDP with value iteration.

State: (estimated sleep debt over previous 3 nights, previous restedness),
       both discretized to low/medium/high.
Action: target sleep duration, which maps to a bedtime for the user's wake time.
Reward: 1-10 next-morning restedness. Sparse transitions and rewards are
smoothed with transparent hand-chosen priors. Not a clinically validated model.
"""

from collections import defaultdict, Counter
from datetime import datetime, timedelta
from itertools import product

TARGET_HOURS = (7.0, 7.5, 8.0, 8.5, 9.0, 9.5)
STATES = list(product(range(3), range(3)))
GAMMA = 0.85
MIN_LOGS_TO_PERSONALIZE = 5


def debt_bucket(debt_hours):
    return 0 if debt_hours < 2 else 1 if debt_hours < 5 else 2


def rested_bucket(score):
    return 0 if score <= 4 else 1 if score <= 7 else 2


def state_from(history):
    if not history:
        return (0, 1)
    debt = sum(max(0.0, 8.0 - night["sleep_hours"]) for night in history[-3:])
    return (debt_bucket(debt), rested_bucket(history[-1]["restedness"]))


def nearest_action(hours):
    return min(TARGET_HOURS, key=lambda candidate: abs(candidate - hours))


def observed_transitions(nights):
    """(state before night, chosen target duration, next state, next restedness)."""
    experiences = []
    for index in range(1, len(nights)):
        history = nights[:index]
        this_night = nights[index]
        experiences.append((
            state_from(history),
            nearest_action(this_night["sleep_hours"]),
            state_from(nights[:index + 1]),
            this_night["restedness"],
        ))
    return experiences


def baseline_reward(state, target_hours):
    """Cold-start prior: 8h is the neutral default, not a user-derived fact."""
    debt_level, _ = state
    return max(1.0, min(10.0, 7.0 - 1.0 * abs(target_hours - 8.0) - 0.35 * debt_level))


def estimate_reward(state, action, experiences):
    # Similar observed durations contribute to an estimate for the action.
    # Data from the same state carry twice the weight of other observations.
    total = 4.0 * baseline_reward(state, action)
    weight = 4.0
    for prior_state, actual_action, _, score in experiences:
        similarity = max(0.0, 1.0 - abs(action - actual_action) / 1.5)
        if similarity == 0:
            continue
        w = similarity * (2.0 if prior_state == state else 0.5)
        total += w * score
        weight += w
    return total / weight


def next_state_prior(state, action, estimated_score):
    # Heuristic pseudo-transition for unobserved (state, action) pairs.
    # Rolling debt is only approximately represented after discretization.
    estimated_debt = (0.5, 3.0, 6.0)[state[0]]
    next_debt = max(0.0, 0.65 * estimated_debt + max(0.0, 8.0 - action)
                    - 0.5 * max(0.0, action - 8.0))
    return (debt_bucket(next_debt), rested_bucket(estimated_score))


def transition_distribution(state, action, experiences, score):
    matches = Counter(
        following for previous, actual, following, _ in experiences
        if previous == state and actual == action
    )
    # Three pseudo-observations prevent a single night from wholly defining
    # a state transition. More matched nights gradually outweigh this prior.
    guess = next_state_prior(state, action, score)
    matches[guess] += 3.0
    total = sum(matches.values())
    return {next_state: count / total for next_state, count in matches.items()}


def solve_mdp(nights):
    experiences = observed_transitions(nights)
    rewards = {}
    transitions = {}
    for state in STATES:
        for action in TARGET_HOURS:
            score = estimate_reward(state, action, experiences)
            rewards[state, action] = score
            transitions[state, action] = transition_distribution(state, action, experiences, score)

    values = {state: 0.0 for state in STATES}
    for _ in range(300):
        next_values = {}
        for state in STATES:
            next_values[state] = max(
                rewards[state, action] + GAMMA * sum(
                    probability * values[next_state]
                    for next_state, probability in transitions[state, action].items()
                )
                for action in TARGET_HOURS
            )
        difference = max(abs(next_values[s] - values[s]) for s in STATES)
        values = next_values
        if difference < 1e-8:
            break

    policy = {}
    for state in STATES:
        policy[state] = max(
            TARGET_HOURS,
            key=lambda action: rewards[state, action] + GAMMA * sum(
                probability * values[next_state]
                for next_state, probability in transitions[state, action].items()
            ),
        )
    return policy, rewards


def recommend(nights, wake_time):
    count = len(nights)
    current_state = state_from(nights)
    if count < MIN_LOGS_TO_PERSONALIZE:
        target_hours = 8.0
        estimated_score = None
        method = "default_8h"
    else:
        policy, rewards = solve_mdp(nights)
        target_hours = policy[current_state]
        estimated_score = round(rewards[current_state, target_hours], 2)
        method = "experimental_mdp"

    clock = datetime.strptime(wake_time, "%H:%M")
    bedtime = (clock - timedelta(hours=target_hours)).strftime("%H:%M")
    return {
        "wake_time": wake_time,
        "suggested_bedtime": bedtime,
        "target_sleep_hours": target_hours,
        "method": method,
        "nights_logged": count,
        "nights_until_personalized": max(0, MIN_LOGS_TO_PERSONALIZE - count),
        "estimated_restedness_score": estimated_score,
        "state": {"sleep_debt": ("low", "medium", "high")[current_state[0]],
                  "previous_restedness": ("low", "medium", "high")[current_state[1]]},
        "disclaimer": "Experimental sleep-habit model, not medical advice or a validated sleep prediction.",
    }


def insights(nights):
    duration_categories = {
        "under_7h": lambda hrs: hrs < 7,
        "7_to_8h": lambda hrs: 7 <= hrs < 8,
        "8_to_9h": lambda hrs: 8 <= hrs < 9,
        "9h_or_more": lambda hrs: hrs >= 9,
    }
    snooze_categories = {
        "0_snoozes": lambda n: n == 0,
        "1_snooze": lambda n: n == 1,
        "2_or_more_snoozes": lambda n: n >= 2,
    }

    def summarize(filtered):
        scores = [night["restedness"] for night in filtered]
        return {"nights": len(scores),
                "average_restedness": round(sum(scores) / len(scores), 2) if scores else None}

    durations = {name: summarize([n for n in nights if predicate(n["sleep_hours"])])
                 for name, predicate in duration_categories.items()}
    snoozes = {name: summarize([n for n in nights if predicate(n["snoozes"])])
               for name, predicate in snooze_categories.items()}
    candidates = [(name, stats["average_restedness"])
                  for name, stats in durations.items() if stats["nights"] >= 2]
    best = max(candidates, key=lambda item: item[1])[0] if candidates else None
    return {
        "nights_logged": len(nights),
        "duration_bins": durations,
        "snooze_bins": snoozes,
        "best_observed_duration_bin": best,
        "note": "Best observed bin requires at least 2 nights; correlations do not prove causation.",
    }
