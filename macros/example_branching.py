"""Image checks and branching: a typical farm loop.

Before running it, use the panel's "Capture image…" button to save these
pictures from your game (names must match):
    play_button   the button that starts a match
    victory       something only shown when you win
    defeat        something only shown when you lose
    replay        the "play again" button on the results screen
"""

ROUNDS = 5


def run(m):
    for round_number in range(1, ROUNDS + 1):
        m.log(f"Round {round_number}/{ROUNDS}")

        # Wait up to 30 s for the play button, then click it.
        if not m.click_image("play_button", timeout=30):
            m.log("Never saw the play button, giving up")
            return

        # Wait up to 10 minutes for the match to end, then pick a path
        # depending on which picture showed up first.
        outcome, match = m.wait_for_any({"win": "victory", "lose": "defeat"}, timeout=600)

        if outcome == "win":
            m.log(f"Won! (seen at {match.center})")
            m.click_image("replay", timeout=10)
        elif outcome == "lose":
            m.log("Lost, waiting a bit before retrying")
            m.wait(5)
            m.click_image("replay", timeout=10)
        else:
            m.log("Match never ended, saving a screenshot to look at")
            m.save_screenshot("stuck")
            return

        m.wait(2)
