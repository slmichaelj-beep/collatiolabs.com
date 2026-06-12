"""marketplaces.upwork — the Upwork bid pipeline tracker (governed, honest).

Tracks the whole funnel for Lamar to watch in real time and for Vera to eventually operate:
jobs scanned → triaged (bid/skip + reason) → bid staged → submitted (Connects spent) → viewed →
replied → interview → awarded → delivered → PAID. Truth is enforced: a submitted bid is activity,
an awarded contract is pipeline, only a PAID contract (with evidence) is collected cash. Connects are
tracked as a finite resource. Vera does not submit bids or send messages — those stay human.
"""
