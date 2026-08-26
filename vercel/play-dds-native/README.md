# PLAY DDS Native — Vercel R86

Isolated Vercel project for PLAY statistical PAR DDS offload.

- Native engine: R86 qualified daemon
- Binary SHA256: `7148b3ee4ecd19b3a9b5205b7a6c23ccb2f42735f80a889e7c95a68af851943a`
- Source blob pinned to immutable commit `77c1e1d9ac6efb7cdd6bd1ddc2eba31c5d5db555`
- Threads: 2
- Batch size: 24
- Max items/request: 24
- Vercel region: Paris (`cdg1`)
- Function memory: 1024 MiB
- Function max duration: 60 s

Health/self-test after deployment:

`GET /api/dds?selftest=1`

Production root directory in Vercel must be:

`vercel/play-dds-native`
