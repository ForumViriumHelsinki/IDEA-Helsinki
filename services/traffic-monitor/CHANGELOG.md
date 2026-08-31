# Changelog

## [0.30.9](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.8...traffic-monitor-v0.30.9) (2026-08-31)


### Bug Fixes

* **deps:** update dependency openfeature-sdk to &gt;=0.10.0,&lt;0.11.0 ([#499](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/499)) ([da4b470](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/da4b4703f1dc0dcd7481de5670b44015fb32379a))

## [0.30.8](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.7...traffic-monitor-v0.30.8) (2026-05-29)


### Bug Fixes

* **traffic-monitor:** correct malformed FCD-mapping retry log message ([#487](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/487)) ([3bfe6f8](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/3bfe6f8a557bc3caba584808ecbb994644ccf279)), closes [#471](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/471) [#486](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/486)

## [0.30.7](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.6...traffic-monitor-v0.30.7) (2026-05-13)


### Bug Fixes

* **traffic-monitor:** close aiohttp session per call in WFS health check ([#470](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/470)) ([0bad4f3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0bad4f3b6b97c9d919124fae883bdaa8d65f77a7))

## [0.30.6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.5...traffic-monitor-v0.30.6) (2026-05-12)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.30.5](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.4...traffic-monitor-v0.30.5) (2026-05-06)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.30.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.3...traffic-monitor-v0.30.4) (2026-05-04)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.30.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.2...traffic-monitor-v0.30.3) (2026-05-04)


### Bug Fixes

* **observability:** demote expected-outcome logs from ERROR to WARNING ([#440](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/440)) ([f3da184](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/f3da1844b075647888f22bd74d4807b80c9b32a3))

## [0.30.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.1...traffic-monitor-v0.30.2) (2026-04-30)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.30.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.30.0...traffic-monitor-v0.30.1) (2026-04-29)


### Bug Fixes

* **json-export:** upload legacy JSON to GCS for TFDS_Dashboard compat ([#425](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/425)) ([f36cc5d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/f36cc5de69ae5747d995d4faea6e9d5eac755de1))

## [0.30.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.29.0...traffic-monitor-v0.30.0) (2026-04-29)


### Features

* **shared:** re-trigger release-please for extended traffic-disturbance model ([#419](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/419)) ([5881f48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/5881f487543a03d8f8c8386988d7d198c9d1ff32))

## [0.29.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.28.1...traffic-monitor-v0.29.0) (2026-04-28)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.28.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.28.0...traffic-monitor-v0.28.1) (2026-04-27)


### Bug Fixes

* **health:** make fcd-manager and traffic-monitor health checks thread-safe ([#404](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/404)) ([348c4e9](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/348c4e9a0d514f03665aced43e7afa9869be5f71))

## [0.28.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.27.0...traffic-monitor-v0.28.0) (2026-04-16)


### Bug Fixes

* **traffic-monitor:** gate fcd_mapping health check on JSON-file mode ([#399](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/399)) ([791933c](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/791933c1277c42d3740492cd7a45799f5d5313fa))

## [0.27.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.26.0...traffic-monitor-v0.27.0) (2026-04-15)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.26.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.25.0...traffic-monitor-v0.26.0) (2026-04-14)


### Features

* introduce ObjectStorageSync protocol and configurable backend factory ([#385](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/385)) ([5dbae63](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/5dbae6362077adaaefd68a06daabac73b64cdfc7))

## [0.25.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.24.0...traffic-monitor-v0.25.0) (2026-04-11)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.24.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.23.4...traffic-monitor-v0.24.0) (2026-04-09)


### Bug Fixes

* **traffic-monitor:** reconnect SQLite after GCS segment download ([#380](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/380)) ([191d77d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/191d77d3f3d23142c326e48f9e4ea03138c7bc85))

## [0.23.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.23.3...traffic-monitor-v0.23.4) (2026-04-08)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.23.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.23.2...traffic-monitor-v0.23.3) (2026-04-07)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.23.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.23.1...traffic-monitor-v0.23.2) (2026-04-07)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.23.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.23.0...traffic-monitor-v0.23.1) (2026-04-01)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.23.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.22.0...traffic-monitor-v0.23.0) (2026-04-01)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.22.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.21.0...traffic-monitor-v0.22.0) (2026-04-01)


### Features

* SQLite migration Phase 4 — service wiring ([#329](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/329)) ([b9d51ed](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b9d51ed1ce3446bb89a602d5fac8936be852e82b))

## [0.21.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.20.0...traffic-monitor-v0.21.0) (2026-03-31)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.20.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.19.0...traffic-monitor-v0.20.0) (2026-03-30)


### Features

* GCS Object API sync layer (Phase 3) ([#324](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/324)) ([fe03f29](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/fe03f29712f39ec6253c039752f3eae39e1e0989))


### Bug Fixes

* resolve ty type checker errors across shared library and services ([#332](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/332)) ([89d5a6b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/89d5a6b1ab045f3d676949556e92cc07408ad3a6))

## [0.19.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.18.1...traffic-monitor-v0.19.0) (2026-03-24)


### Features

* replace pyright with ty for type checking ([#319](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/319)) ([3cd7594](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/3cd75945f578b41125a3a838eba77a16137348cf))

## [0.18.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.18.0...traffic-monitor-v0.18.1) (2026-03-20)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.18.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.17.0...traffic-monitor-v0.18.0) (2026-03-20)


### Features

* add data access layer for SQLite migration (Phase 1) ([#294](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/294)) ([c701e7f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c701e7f42681740326e184038144f08c5fd6c1b9))

## [0.17.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.16.0...traffic-monitor-v0.17.0) (2026-03-20)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.16.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.15.0...traffic-monitor-v0.16.0) (2026-03-18)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.15.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.14.4...traffic-monitor-v0.15.0) (2026-03-18)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.14.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.14.3...traffic-monitor-v0.14.4) (2026-03-18)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.14.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.14.2...traffic-monitor-v0.14.3) (2026-03-17)


### Documentation

* add project rules and apply ruff formatting ([#265](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/265)) ([4bd90da](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/4bd90da7bc12ba2c41916f0b0bc5210c8519316f))

## [0.14.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.14.1...traffic-monitor-v0.14.2) (2026-03-09)


### Bug Fixes

* **deps:** update dependency openfeature-sdk to &gt;=0.8.4,&lt;0.9.0 ([#243](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/243)) ([92328ae](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/92328ae3f975ee187a1652e7e02a45f77e00575f))

## [0.14.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.14.0...traffic-monitor-v0.14.1) (2026-03-09)


### Documentation

* improve documentation and apply formatting corrections ([#255](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/255)) ([385edae](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/385edaefe62c030c5254fb32f24d9557ab6e803d)), closes [#13](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/13)

## [0.14.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.13.2...traffic-monitor-v0.14.0) (2026-02-24)


### Features

* add segment buffering and improve validation initialization from dev branch ([#231](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/231)) ([bbbc33a](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/bbbc33ab324f0b3dedd16a8c1b34607c46743ea3))

## [0.13.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.13.1...traffic-monitor-v0.13.2) (2026-02-17)


### Documentation

* add project rules and improve README documentation ([#222](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/222)) ([0826989](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0826989b2274f89087eca630c35dbe41f7e43c12))

## [0.13.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.13.0...traffic-monitor-v0.13.1) (2026-02-17)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.13.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.12.6...traffic-monitor-v0.13.0) (2026-02-17)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.12.6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.12.5...traffic-monitor-v0.12.6) (2026-02-15)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.12.5](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.12.4...traffic-monitor-v0.12.5) (2026-02-14)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.12.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.12.3...traffic-monitor-v0.12.4) (2026-02-13)


### Bug Fixes

* address PR [#185](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/185) review feedback ([#190](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/190)) ([311fb60](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/311fb6028e14e1341c39eb8b243b27fac344a699))

## [0.12.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.12.2...traffic-monitor-v0.12.3) (2026-02-13)


### Bug Fixes

* add retry logic for WFS and InfluxDB transient failures ([#185](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/185)) ([347a311](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/347a311fa48fa6a2301932fd09cf3d3ca43d5307))

## [0.12.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.12.1...traffic-monitor-v0.12.2) (2026-02-13)


### Bug Fixes

* resolve container build and lint workflow issues from uv workspace migration ([#178](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/178)) ([d19f203](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/d19f2030ff67c3c925cdafc1090bd2790b0d5087)), closes [#174](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/174)

## [0.12.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.12.0...traffic-monitor-v0.12.1) (2026-02-13)


### Bug Fixes

* optimize InfluxDB health check queries with field filters ([#176](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/176)) ([02955a6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/02955a682c65d74a84bf78aff4a8a3cbaf3d23be)), closes [#35](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/35)

## [0.12.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.11.4...traffic-monitor-v0.12.0) (2026-02-12)


### Features

* migrate IDEA-Helsinki to uv workspace ([#174](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/174)) ([76c5daa](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/76c5daaff941909f6f1d1ef671ab2fe264de840a))

## [0.11.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.11.3...traffic-monitor-v0.11.4) (2026-02-11)


### Bug Fixes

* preserve repo directory structure in Docker builds instead of sed hack ([b2c68dd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b2c68dd0551ac924f3fdd4e56745aeae46b15001))
* rewrite shared library path in Dockerfiles for container builds ([9d7550d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/9d7550d28fc7afa62cd0e844296daaa4ee9853c6))

## [0.11.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.11.2...traffic-monitor-v0.11.3) (2026-02-11)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.11.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.11.1...traffic-monitor-v0.11.2) (2026-02-05)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.11.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.11.0...traffic-monitor-v0.11.1) (2026-01-30)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.11.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.10.0...traffic-monitor-v0.11.0) (2026-01-29)


### Features

* migrate IDEA-Helsinki to GoFeatureFlag relay proxy ([#149](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/149)) ([c8fcd2e](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c8fcd2eb6323d3e9dca1df36ca7184e6f673df4f))

## [0.10.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.9.1...traffic-monitor-v0.10.0) (2026-01-15)


### Features

* **health:** add startup-specific health checks to traffic-monitor service ([#141](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/141)) ([0d33a6f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0d33a6f7bf8d34ef0f558aa9478cf9400d6850a0))
* Implement multi-threaded processing for FCD Manager ([#105](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/105)) ([#114](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/114)) ([b90f486](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b90f486659f62f444245379a049329cb6e49a607))

## [0.9.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.9.0...traffic-monitor-v0.9.1) (2025-11-10)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki versions

## [0.9.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.6.2...traffic-monitor-v0.9.0) (2025-10-24)


### Miscellaneous Chores

* **traffic-monitor:** Synchronize idea-helsinki-services versions

## [0.6.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.6.1...traffic-monitor-v0.6.2) (2025-10-21)


### Bug Fixes

* **services:** update for idea-shared module changes ([#121](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/121)) ([26039d3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/26039d32ec5b4244635272628054742bba85afea))

## [0.6.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.6.0...traffic-monitor-v0.6.1) (2025-10-20)


### Bug Fixes

* add pytest asyncio_mode configuration to prevent test hangs ([#120](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/120)) ([260b1bf](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/260b1bf038705ddb496eea8ee96160b98e48c1e0)), closes [#119](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/119)

## [0.6.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.5.0...traffic-monitor-v0.6.0) (2025-10-20)


### Features

* adjust Sentry SDK sample rate to 0.1 for quota management ([#112](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/112)) ([840072d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/840072dfb60c1bc55b623b2a466b060fceda0155)), closes [#111](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/111)

## [0.5.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.4.2...traffic-monitor-v0.5.0) (2025-10-15)


### Features

* Add comprehensive testing infrastructure with pytest ([#100](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/100)) ([0bb57dd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0bb57dd565d6b9cccefd4d7a09af5ae2ae3baddc))

## [0.4.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.4.1...traffic-monitor-v0.4.2) (2025-10-10)


### Bug Fixes

* **services:** update for idea-shared module changes ([#94](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/94)) ([1ac1981](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/1ac1981d648068b1aba14478024d07cf06756509))

## [0.4.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.4.0...traffic-monitor-v0.4.1) (2025-10-08)


### Bug Fixes

* remove version pinning for idea-shared in services ([#85](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/85)) ([b2ab907](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b2ab9072f719a807d5c143857b069b0c42733352))

## [0.4.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.3.3...traffic-monitor-v0.4.0) (2025-10-08)


### Features

* configure Sentry for all IDEA-Helsinki services ([#80](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/80)) ([ec99d37](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/ec99d37366625d15e9419c0190978b9e4f32907a)), closes [#79](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/79)

## [0.3.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.3.2...traffic-monitor-v0.3.3) (2025-10-07)


### Bug Fixes

* trigger service releases for idea-shared 0.2.1 ([#76](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/76)) ([296b85c](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/296b85c507e6861ceac6cd000df50f263425965d))

## [0.3.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.3.1...traffic-monitor-v0.3.2) (2025-10-06)


### Bug Fixes

* release-please workspace configuration and dependency tracking ([#64](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/64)) ([fdb1f93](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/fdb1f93c9c5e3ed9edf45126c19730252d795fc2))

## [0.3.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.3.0...traffic-monitor-v0.3.1) (2025-10-02)


### Bug Fixes

* **idea-helsinki:** add required parameters to DatabaseHealthCheck initialization ([#48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/48)) ([6ecac59](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/6ecac59193c2376fccc75f2203a53b877e02ff96))

## [0.3.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.2.2...traffic-monitor-v0.3.0) (2025-09-30)


### Features

* **traffic-monitor:** implement health checks for Traffic Monitor service ([#43](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/43)) ([187f8f8](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/187f8f85532290a8e875ff11b385057a9fd53751))

## [0.2.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.2.1...traffic-monitor-v0.2.2) (2025-09-08)


### Bug Fixes

* resolve Docker build context issues for all services ([#20](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/20)) ([d246ad2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/d246ad288136f9fd8c05aa5a3835503dd2ce8f7b))

## [0.2.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.2.0...traffic-monitor-v0.2.1) (2025-09-08)


### Bug Fixes

* correct Docker build context paths for GitHub Actions ([#18](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/18)) ([86b6f48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/86b6f48f6229cc32eef156b274f1a88fbb33443f))

## [0.2.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/traffic-monitor-v0.1.0...traffic-monitor-v0.2.0) (2025-09-04)


### Features

* Containerize Python services with modern development workflow ([c20441a](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c20441a493c94af665182ed360685c67cb0053c7))
