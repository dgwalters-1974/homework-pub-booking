# Booking validator — rejected

- Timestamp (UTC): 2026-05-19T14:53:40Z
- Profile: `slide`
- Outcome: **rejected**
- Reason: `vegan_ratio_too_high`

## Policy applied
- max_party_size: 170
- max_deposit_gbp: 300
- max_vegan_ratio: 0.8

## Booking payload
```json
{
  "venue_id": "haymarket_tap",
  "date": "2026-05-19",
  "time": "17:00",
  "party_size": 160,
  "deposit_gbp": 300,
  "duration_hours": 3,
  "catering_tier": "bar_snacks",
  "policy_profile": "slide",
  "vegan_ratio": 0.9
}
```
