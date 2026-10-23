# Trading Lab agent rules

Work in an isolated, non-custodial research system.

- Do not connect to live trade-order endpoints or access 0xda-market core payments, orders, wallets, or secrets.
- Maintain explicit provenance for source timestamps, collection timestamps, and prices. Never use future data for a historical fill.
- Prefer deterministic simulations, Decimal money values, finite position sizing, and clear failures over optimistic performance claims.
- Each independent change uses a feature/ or fix/ branch and one draft PR based on the latest default branch.
- Do not commit directly to the default branch. The empty-repository LICENSE initialization was a one-time prerequisite before a branch could exist.
- Full CI verifies correctness; deployment validation, if introduced later, checks deployment readiness without repeating Full CI.
- Merge and deployment remain separate actions and require explicit authorization. Do not deploy automatically.
- Add tests for any change to strategy performance or execution assumptions.
- Follow the repo MIT LICENSE and the organization copyright-header policy.

© 2026 aiaiaiai · aiaiaiai.org
