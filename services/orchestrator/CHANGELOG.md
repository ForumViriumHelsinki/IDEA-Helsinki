# Changelog

## [0.12.6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.12.5...orchestrator-v0.12.6) (2026-02-15)


### Miscellaneous Chores

* **orchestrator:** Synchronize idea-helsinki versions

## [0.12.5](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.12.4...orchestrator-v0.12.5) (2026-02-14)


### Miscellaneous Chores

* **orchestrator:** Synchronize idea-helsinki versions

## [0.12.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.12.3...orchestrator-v0.12.4) (2026-02-13)


### Miscellaneous Chores

* **orchestrator:** Synchronize idea-helsinki versions

## [0.12.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.12.2...orchestrator-v0.12.3) (2026-02-13)


### Bug Fixes

* add retry logic for WFS and InfluxDB transient failures ([#185](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/185)) ([347a311](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/347a311fa48fa6a2301932fd09cf3d3ca43d5307))

## [0.12.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.12.1...orchestrator-v0.12.2) (2026-02-13)


### Bug Fixes

* resolve container build and lint workflow issues from uv workspace migration ([#178](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/178)) ([d19f203](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/d19f2030ff67c3c925cdafc1090bd2790b0d5087)), closes [#174](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/174)

## [0.12.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.12.0...orchestrator-v0.12.1) (2026-02-13)


### Bug Fixes

* optimize InfluxDB health check queries with field filters ([#176](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/176)) ([02955a6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/02955a682c65d74a84bf78aff4a8a3cbaf3d23be)), closes [#35](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/35)

## [0.12.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.11.4...orchestrator-v0.12.0) (2026-02-12)


### Features

* migrate IDEA-Helsinki to uv workspace ([#174](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/174)) ([76c5daa](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/76c5daaff941909f6f1d1ef671ab2fe264de840a))

## [0.11.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.11.3...orchestrator-v0.11.4) (2026-02-11)


### Bug Fixes

* preserve repo directory structure in Docker builds instead of sed hack ([b2c68dd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b2c68dd0551ac924f3fdd4e56745aeae46b15001))
* rewrite shared library path in Dockerfiles for container builds ([9d7550d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/9d7550d28fc7afa62cd0e844296daaa4ee9853c6))

## [0.11.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.11.2...orchestrator-v0.11.3) (2026-02-11)


### Miscellaneous Chores

* **orchestrator:** Synchronize idea-helsinki versions

## [0.11.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.11.1...orchestrator-v0.11.2) (2026-02-05)


### Miscellaneous Chores

* **orchestrator:** Synchronize idea-helsinki versions

## [0.11.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.11.0...orchestrator-v0.11.1) (2026-01-30)


### Miscellaneous Chores

* **orchestrator:** Synchronize idea-helsinki versions

## [0.11.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.10.0...orchestrator-v0.11.0) (2026-01-29)


### Features

* migrate IDEA-Helsinki to GoFeatureFlag relay proxy ([#149](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/149)) ([c8fcd2e](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c8fcd2eb6323d3e9dca1df36ca7184e6f673df4f))

## [0.10.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.9.1...orchestrator-v0.10.0) (2026-01-15)


### Features

* **health:** add startup-specific health checks to orchestrator service ([#140](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/140)) ([3f29264](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/3f292640ea3e1e5e84f2a8e141d24a733d0113bd))
* **health:** add startup-specific health checks to traffic-monitor service ([#141](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/141)) ([0d33a6f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0d33a6f7bf8d34ef0f558aa9478cf9400d6850a0))
* Implement multi-threaded processing for FCD Manager ([#105](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/105)) ([#114](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/114)) ([b90f486](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b90f486659f62f444245379a049329cb6e49a607))

## [0.9.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.9.0...orchestrator-v0.9.1) (2025-11-10)


### Bug Fixes

* **health:** convert PosixPath to string in health check metadata ([#130](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/130)) ([78ebae0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/78ebae051a0791d33fe7656bb347e0d2d579ee10))

## [0.9.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.8.1...orchestrator-v0.9.0) (2025-10-24)


### Features

* implement async context manager for InfluxDBConnectionManager ([#127](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/127)) ([f7fc26f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/f7fc26f61fb40a779ccca27e9f76ff9a669bbb8d)), closes [#31](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/31)

## [0.8.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.8.0...orchestrator-v0.8.1) (2025-10-21)


### Bug Fixes

* **services:** update for idea-shared module changes ([#121](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/121)) ([26039d3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/26039d32ec5b4244635272628054742bba85afea))

## [0.8.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/orchestrator-v0.7.0...orchestrator-v0.8.0) (2025-10-20)


### Features

* rename container image to orchestrator ([#83](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/83)) ([230e15f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/230e15ff14c22b8b85f4f475024b534ce75e5bb7))


### Bug Fixes

* add pytest asyncio_mode configuration to prevent test hangs ([#120](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/120)) ([260b1bf](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/260b1bf038705ddb496eea8ee96160b98e48c1e0)), closes [#119](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/119)
* trigger service releases for idea-shared 0.2.1 ([#76](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/76)) ([296b85c](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/296b85c507e6861ceac6cd000df50f263425965d))

## [0.7.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.6.0...idea-helsinki-v0.7.0) (2025-10-20)


### Features

* adjust Sentry SDK sample rate to 0.1 for quota management ([#112](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/112)) ([840072d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/840072dfb60c1bc55b623b2a466b060fceda0155)), closes [#111](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/111)

## [0.6.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.5.0...idea-helsinki-v0.6.0) (2025-10-17)


### Features

* add backfill mode detection to health checks ([#107](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/107)) ([6de35df](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/6de35df21db131c578ee331304ac5980950d9713))

## [0.5.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.4.2...idea-helsinki-v0.5.0) (2025-10-15)


### Features

* Add comprehensive testing infrastructure with pytest ([#100](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/100)) ([0bb57dd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0bb57dd565d6b9cccefd4d7a09af5ae2ae3baddc))

## [0.4.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.4.1...idea-helsinki-v0.4.2) (2025-10-10)


### Bug Fixes

* **services:** update for idea-shared module changes ([#94](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/94)) ([1ac1981](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/1ac1981d648068b1aba14478024d07cf06756509))

## [0.4.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.4.0...idea-helsinki-v0.4.1) (2025-10-08)


### Bug Fixes

* remove version pinning for idea-shared in services ([#85](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/85)) ([b2ab907](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b2ab9072f719a807d5c143857b069b0c42733352))

## [0.4.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.3.7...idea-helsinki-v0.4.0) (2025-10-08)


### Features

* configure Sentry for all IDEA-Helsinki services ([#80](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/80)) ([ec99d37](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/ec99d37366625d15e9419c0190978b9e4f32907a)), closes [#79](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/79)

## [0.3.7](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.3.6...idea-helsinki-v0.3.7) (2025-10-07)


### Bug Fixes

* trigger service releases for idea-shared 0.2.1 ([#76](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/76)) ([296b85c](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/296b85c507e6861ceac6cd000df50f263425965d))

## [0.3.6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.3.5...idea-helsinki-v0.3.6) (2025-10-07)


### Bug Fixes

* resolve syntax error in WorkerStatusHealthCheck initialization ([#67](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/67)) ([8a61820](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/8a61820353311f9e97693f86a933bbabcc3fdddb)), closes [#66](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/66)

## [0.3.5](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.3.4...idea-helsinki-v0.3.5) (2025-10-06)


### Bug Fixes

* prevent memory leak in WorkerStatusHealthCheck ([#62](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/62)) ([31ba4f3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/31ba4f3b02fbbf6339b08e62a1d1728fa65278a2))
* release-please workspace configuration and dependency tracking ([#64](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/64)) ([fdb1f93](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/fdb1f93c9c5e3ed9edf45126c19730252d795fc2))

## [0.3.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.3.3...idea-helsinki-v0.3.4) (2025-10-06)


### Bug Fixes

* add missing name parameter to all HealthCheckResult instances ([#59](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/59)) ([0653b03](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0653b03da774afe03f2a2f5888e102cc0b0f4341))
* externalize health check configuration constants ([#55](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/55)) ([8b19327](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/8b19327b040d9038ad507904d546cf4e27f415cd))

## [0.3.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.3.2...idea-helsinki-v0.3.3) (2025-10-03)


### Bug Fixes

* enhance error messages in health checks ([#53](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/53)) ([fe0e250](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/fe0e250fbad3ce6f7c5c39d069c52c3a2eb64283))

## [0.3.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.3.1...idea-helsinki-v0.3.2) (2025-10-03)


### Bug Fixes

* add missing name parameter to DisturbanceDataHealthCheck ([#51](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/51)) ([bb2323e](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/bb2323e03c7284e37c25bcf2e58b4c3c6e45e358)), closes [#50](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/50)

## [0.3.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.3.0...idea-helsinki-v0.3.1) (2025-10-02)


### Bug Fixes

* **idea-helsinki:** add required parameters to DatabaseHealthCheck initialization ([#48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/48)) ([6ecac59](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/6ecac59193c2376fccc75f2203a53b877e02ff96))

## [0.3.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.2.2...idea-helsinki-v0.3.0) (2025-09-30)


### Features

* Implement health checks for FCD Manager service ([#42](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/42)) ([e3755a6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/e3755a6c4b04c9ca93ba96e7d877fe778e1d42ed))
* Implement health checks for IDEA Helsinki service ([#30](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/30)) ([6fb327f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/6fb327f52e43fc3344a342e8841a8c6155b6b893))

## [0.2.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.2.1...idea-helsinki-v0.2.2) (2025-09-08)


### Bug Fixes

* resolve Docker build context issues for all services ([#20](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/20)) ([d246ad2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/d246ad288136f9fd8c05aa5a3835503dd2ce8f7b))

## [0.2.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.2.0...idea-helsinki-v0.2.1) (2025-09-08)


### Bug Fixes

* correct Docker build context paths for GitHub Actions ([#18](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/18)) ([86b6f48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/86b6f48f6229cc32eef156b274f1a88fbb33443f))

## [0.2.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-helsinki-v0.1.0...idea-helsinki-v0.2.0) (2025-09-04)


### Features

* Containerize Python services with modern development workflow ([c20441a](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c20441a493c94af665182ed360685c67cb0053c7))
