Ideas for the teams feature

- The teams are primarily created via roles. The bot follows Discord roles as it can
- Re-scans rolls on startup and re-syncs teams with roles
- When does point awarding happen?
  - Totally configurable. Frequency, point amount, etc.
  - Points are awarded based on state data at a moment. Team joining datetime is kept, but only for recordkeeping
    Also called "milestone scoring", in that crossing a milestone and the state at that point is the only thing considered
- How do handle a non-scoring joining period?
  - Find out if this feature is wanted
  - Does percentage of time on the team that day matter?