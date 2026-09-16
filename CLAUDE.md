# FootballSlop notes for Claude

- The production Render service (free tier) is kept awake by an external
  cron job that pings the page every 10 minutes, so the dyno does not spin
  down from inactivity. Don't assume the app can go to sleep mid-day and
  miss a scheduled snap/results job purely from idleness — plan around it
  staying up continuously instead.
