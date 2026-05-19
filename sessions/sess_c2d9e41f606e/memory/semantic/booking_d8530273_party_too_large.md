# Booking validator — rejected

- Timestamp (UTC): 2026-05-19T14:53:28Z
- Profile: `default`
- Outcome: **rejected**
- Reason: `party_too_large`

## Policy applied
- max_party_size: 8
- max_deposit_gbp: 300
- max_vegan_ratio: None

## Booking payload
```json
{
  "venue_id": "haymarket_tap",
  "date": "2026-04-25",
  "time": "19:30",
  "party_size": 12,
  "deposit_gbp": 0,
  "duration_hours": 3,
  "catering_tier": "bar_snacks",
  "policy_profile": "default"
}
```
