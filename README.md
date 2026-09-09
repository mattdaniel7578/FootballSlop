# FootballSlop

A simple pick'em pool for ~20 friends picking NFL games against the spread.

## Setup

1. **Create a virtualenv and install dependencies**

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Create a Google OAuth client**

   - Go to https://console.cloud.google.com/apis/credentials
   - Create an "OAuth client ID" of type "Web application"
   - Add authorized redirect URI: `http://localhost:5000/auth/callback`
   - Copy the Client ID and Client Secret

3. **Configure environment variables**

   ```powershell
   copy .env.example .env
   ```

   Edit `.env` and fill in `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   and `ADMIN_EMAILS` (your own Google account email — comma-separate for
   multiple admins).

4. **Run the app**

   ```powershell
   python app.py
   ```

   Visit http://localhost:5000

## Using it

- Log in with Google (top right).
- An admin (an email listed in `ADMIN_EMAILS`) sees an "Add game" link to
  create games and enter the current DraftKings spread by hand.
- Everyone else logs in and picks a side for each open game. Picks can be
  changed until kickoff.

To add the season opener, log in as an admin and use "Add game" with:
- Home team / Away team: whichever DraftKings lists as home/away
- Favorite team + spread points: read directly off the DraftKings spread
  for Seahawks @ Patriots
- Kickoff time in UTC

## Notes / what's next

- Spreads are entered manually for now (see `odds.py` for a sketch of how
  to wire up a live odds API like https://the-odds-api.com/ later).
- No scoring/standings yet — picks are just recorded per user per game.
- SQLite database file (`pool.db`) is created automatically on first run.
