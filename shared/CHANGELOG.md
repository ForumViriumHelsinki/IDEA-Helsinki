# Changelog

## [0.30.9](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.8...idea-shared-v0.30.9) (2026-08-31)


### Bug Fixes

* **deps:** update dependency openfeature-sdk to &gt;=0.10.0,&lt;0.11.0 ([#499](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/499)) ([da4b470](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/da4b4703f1dc0dcd7481de5670b44015fb32379a))


### Documentation

* **feature-flags:** correct GOFF service name in provider docstring ([#493](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/493)) ([23e2c5b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/23e2c5bf48109adb3241415a65787387d659f81e))

## [0.30.8](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.7...idea-shared-v0.30.8) (2026-05-29)


### Miscellaneous Chores

* **idea-shared:** Synchronize idea-helsinki versions

## [0.30.7](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.6...idea-shared-v0.30.7) (2026-05-13)


### Bug Fixes

* **sqlite:** self-heal corrupt disturbances DB to break crash-loop ([#469](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/469)) ([b49e0b7](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b49e0b7c1971b5c31ee01c7d731d1108bd3e640a))
* **sqlite:** self-heal schema when expected tables are missing ([#467](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/467)) ([85e9683](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/85e9683b773586c82973e18006aa00203c1c1ffa))
* strictly validate and filter disturbance dates upstream ([#449](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/449)) ([5958695](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/595869520618b42719fe17d2238d15ad489bab14))

## [0.30.6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.5...idea-shared-v0.30.6) (2026-05-12)


### Bug Fixes

* **feature-flags:** pass GOFF_API_KEY through to the relay proxy ([#462](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/462)) ([7aa22f9](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/7aa22f94486651b9003f2921a06b98c8fcf86282))

## [0.30.5](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.4...idea-shared-v0.30.5) (2026-05-06)


### Bug Fixes

* **orchestrator:** reconnect SQLite after disturbances download ([#454](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/454)) ([d0d0499](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/d0d0499d52b71a4e3a0cb330886b47dc355dd2b9))

## [0.30.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.3...idea-shared-v0.30.4) (2026-05-04)


### Bug Fixes

* **health:** resolve InfluxDB read timeouts in backfill mode checks ([#439](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/439)) ([4d6b74b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/4d6b74b90eca51306e784e657a314b3601616507))
* idea-validation-memory-optimisation ([#446](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/446)) ([7c654d8](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/7c654d8de85d7296edd6e1d0a6fb92022a14fcb7))

## [0.30.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.2...idea-shared-v0.30.3) (2026-05-04)


### Bug Fixes

* **observability:** demote expected-outcome logs from ERROR to WARNING ([#440](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/440)) ([f3da184](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/f3da1844b075647888f22bd74d4807b80c9b32a3))

## [0.30.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.1...idea-shared-v0.30.2) (2026-04-30)


### Bug Fixes

* **sqlite:** resolve thread/type/null bugs in profile repository ([#432](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/432)) ([c741ccd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c741ccd2ec67b97956e53f2c83ea33cb34026c65))

## [0.30.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.30.0...idea-shared-v0.30.1) (2026-04-29)


### Bug Fixes

* **json-export:** upload legacy JSON to GCS for TFDS_Dashboard compat ([#425](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/425)) ([f36cc5d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/f36cc5de69ae5747d995d4faea6e9d5eac755de1))

## [0.30.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.29.0...idea-shared-v0.30.0) (2026-04-29)


### Features

* **shared:** re-trigger release-please for extended traffic-disturbance model ([#419](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/419)) ([5881f48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/5881f487543a03d8f8c8386988d7d198c9d1ff32))

## [0.29.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.28.1...idea-shared-v0.29.0) (2026-04-28)


### Features

* **orchestrator:** wire SQLite profile storage for segment workers ([#406](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/406)) ([823c17f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/823c17fa1777211998aecc0c3aa01e5a3db070d2))

## [0.28.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.28.0...idea-shared-v0.28.1) (2026-04-27)


### Bug Fixes

* align InfluxDB measurement names between producers and health checks ([#405](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/405)) ([047cbdb](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/047cbdbbd10bcacda21dcb5dadfd8ae8d9cb5ace))

## [0.28.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.27.0...idea-shared-v0.28.0) (2026-04-16)


### Features

* lookback window for cross-cycle segment geo-inheritance ([#395](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/395)) ([4c4c2ac](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/4c4c2acb740d3430bc532b0e5eaa86eaae8a7efd))

## [0.27.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.26.0...idea-shared-v0.27.0) (2026-04-15)


### Features

* migrate InfluxDB timeseries on segment geo-inheritance ([#391](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/391)) ([4ec879d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/4ec879d053f8553c19fed7159a1871794262ce36))

## [0.26.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.25.0...idea-shared-v0.26.0) (2026-04-14)


### Features

* introduce ObjectStorageSync protocol and configurable backend factory ([#385](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/385)) ([5dbae63](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/5dbae6362077adaaefd68a06daabac73b64cdfc7))

## [0.25.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.24.0...idea-shared-v0.25.0) (2026-04-11)


### Features

* breadcrumb filtering to reduce InfluxDB noise in Sentry ([#386](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/386)) ([29a1813](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/29a1813dd82e054404e70677e0df254ce333a9e4))

## [0.24.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.23.4...idea-shared-v0.24.0) (2026-04-09)


### Bug Fixes

* **traffic-monitor:** reconnect SQLite after GCS segment download ([#380](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/380)) ([191d77d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/191d77d3f3d23142c326e48f9e4ea03138c7bc85))

## [0.23.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.23.3...idea-shared-v0.23.4) (2026-04-08)


### Bug Fixes

* prevent CancelledError in uvicorn lifespan during graceful shutdown ([#377](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/377)) ([e6f4f9f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/e6f4f9f5c73895f4d0f3ea0f43f4a19e0a6d517f))

## [0.23.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.23.2...idea-shared-v0.23.3) (2026-04-07)


### Miscellaneous Chores

* **idea-shared:** Synchronize idea-helsinki versions

## [0.23.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.23.1...idea-shared-v0.23.2) (2026-04-07)


### Bug Fixes

* remove doubled GCS prefix ([#363](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/363)) ([d861be2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/d861be2ead0e6d3d1aa5f440f49edae25cbedc9b))

## [0.23.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.23.0...idea-shared-v0.23.1) (2026-04-01)


### Bug Fixes

* IDEA profile creation with less FCD ([#353](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/353)) ([8501f5b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/8501f5b32d14f88fa5843fb1205983f60aba316f))

## [0.23.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.22.0...idea-shared-v0.23.0) (2026-04-01)


### Features

* sQLite storage by default across all deployments ([#350](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/350)) ([9ed4746](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/9ed4746aa3011c98a967129b3bf6f91e34c5f921))

## [0.22.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.21.0...idea-shared-v0.22.0) (2026-04-01)


### Features

* SQLite migration Phase 4 — service wiring ([#329](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/329)) ([b9d51ed](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b9d51ed1ce3446bb89a602d5fac8936be852e82b))

## [0.21.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.20.0...idea-shared-v0.21.0) (2026-03-31)


### Features

* **sentry:** add service tag to distinguish events per service ([#340](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/340)) ([e6663fd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/e6663fdb0bcabdf2308ac7287c568bb4a4781a0c))


### Bug Fixes

* update profile time frame. ([#342](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/342)) ([28ce570](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/28ce570396f3752618585b8f57d288b4aef95b28))


### Performance Improvements

* **sentry:** tune sampling rates and make configurable via env vars ([#339](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/339)) ([3e218dc](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/3e218dc2118fd1ba5f3f4fbdab8a3ed3d4a919ac))

## [0.20.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.19.0...idea-shared-v0.20.0) (2026-03-30)


### Features

* GCS Object API sync layer (Phase 3) ([#324](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/324)) ([fe03f29](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/fe03f29712f39ec6253c039752f3eae39e1e0989))
* SQLite backend implementations (Phase 2) ([#311](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/311)) ([c547133](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c5471334c7bf6122b6e04c580a8f5a2a46925ad9))


### Bug Fixes

* resolve ty type checker errors across shared library and services ([#332](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/332)) ([89d5a6b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/89d5a6b1ab045f3d676949556e92cc07408ad3a6))

## [0.19.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.18.1...idea-shared-v0.19.0) (2026-03-24)


### Features

* configure Sentry release tracking and deploy notifications ([#318](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/318)) ([342528e](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/342528ed3e557d4f1f072b6f4b3fb1f750597a8f))
* replace pyright with ty for type checking ([#319](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/319)) ([3cd7594](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/3cd75945f578b41125a3a838eba77a16137348cf))


### Bug Fixes

* prevent empty InfluxDB range query when profiling ends today ([#316](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/316)) ([76eeffe](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/76eeffe450f161391ad7a5e5c11fa671e96d50bb))

## [0.18.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.18.0...idea-shared-v0.18.1) (2026-03-20)


### Bug Fixes

* improve WFS 400 error diagnostics and logging clarity ([#306](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/306)) ([2b5ff88](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/2b5ff881952c6c567843f0bd10b64250e617e55e))

## [0.18.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.17.0...idea-shared-v0.18.0) (2026-03-20)


### Features

* add data access layer for SQLite migration (Phase 1) ([#294](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/294)) ([c701e7f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c701e7f42681740326e184038144f08c5fd6c1b9))

## [0.17.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.16.0...idea-shared-v0.17.0) (2026-03-20)


### Features

* inherit segment history when replaced segments match geographically ([#290](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/290)) ([4a6f6c2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/4a6f6c2996ce8ce85e1b67e12009a94b648aa5ba))

## [0.16.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.15.0...idea-shared-v0.16.0) (2026-03-18)


### Features

* add health check execution time tracking and slow check warnings ([#285](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/285)) ([1fedb4b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/1fedb4bd676c0684e625be0b930c6ad479bad3c8))


### Bug Fixes

* avoid mutating caller's query_fields list in get_segment_data_dataframe ([#288](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/288)) ([f3b4bde](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/f3b4bde9f02d4e38bbb60b1822931feb1e837949))
* cap dead-letter queue size in DateRangeQueue ([#286](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/286)) ([a9a4756](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/a9a47567f32c9a56b9772b87e8a0eea97a46bef5))
* store and cancel health server asyncio task on shutdown ([#287](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/287)) ([2d74130](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/2d7413018ac9d0e8a9bceb332039f4bf976e67d9))

## [0.15.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.14.4...idea-shared-v0.15.0) (2026-03-18)


### Features

* add validation semaphore and configurable history window ([#280](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/280)) ([f6fa4e3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/f6fa4e3721704e687f0dc79b07a83b6951c1e373))

## [0.14.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.14.3...idea-shared-v0.14.4) (2026-03-18)


### Performance Improvements

* reduce orchestrator memory via chunked profile queries and semaphore ([#274](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/274)) ([36561db](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/36561db27ff380e7258522427a8e735afaa91f65))

## [0.14.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.14.2...idea-shared-v0.14.3) (2026-03-17)


### Bug Fixes

* resolve orchestrator OOMKill (4Gi → 6Gi) ([#268](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/268)) ([c0ab5a2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c0ab5a28a7d1f1f4fda1be37d8e19aea0f52b57b))


### Documentation

* add project rules and apply ruff formatting ([#265](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/265)) ([4bd90da](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/4bd90da7bc12ba2c41916f0b0bc5210c8519316f))

## [0.14.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.14.1...idea-shared-v0.14.2) (2026-03-09)


### Bug Fixes

* **deps:** update dependency openfeature-sdk to &gt;=0.8.4,&lt;0.9.0 ([#243](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/243)) ([92328ae](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/92328ae3f975ee187a1652e7e02a45f77e00575f))

## [0.14.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.14.0...idea-shared-v0.14.1) (2026-03-09)


### Documentation

* improve documentation and apply formatting corrections ([#255](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/255)) ([385edae](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/385edaefe62c030c5254fb32f24d9557ab6e803d)), closes [#13](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/13)

## [0.14.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.13.2...idea-shared-v0.14.0) (2026-02-24)


### Features

* add segment buffering and improve validation initialization from dev branch ([#231](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/231)) ([bbbc33a](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/bbbc33ab324f0b3dedd16a8c1b34607c46743ea3))

## [0.13.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.13.1...idea-shared-v0.13.2) (2026-02-17)


### Documentation

* add project rules and improve README documentation ([#222](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/222)) ([0826989](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0826989b2274f89087eca630c35dbe41f7e43c12))

## [0.13.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.13.0...idea-shared-v0.13.1) (2026-02-17)


### Bug Fixes

* add ESTALE retry to JSON file reads for GCS FUSE ([#217](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/217)) ([0974f2b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0974f2b01ef35d2bd00b19027c76020456759494))

## [0.13.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.12.6...idea-shared-v0.13.0) (2026-02-17)


### Features

* add production-grade resilience infrastructure to prevent cascade failures ([#211](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/211)) ([8784acc](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/8784acc66b3b0d58098f358345f244c7fc766111))

## [0.12.6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.12.5...idea-shared-v0.12.6) (2026-02-15)


### Bug Fixes

* resolve health check failures blocking fcd-manager and orchestrator readiness ([#206](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/206)) ([aa25fa9](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/aa25fa9263f36679d5e9fbcd5ff8fed433a8270a))

## [0.12.5](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.12.4...idea-shared-v0.12.5) (2026-02-14)


### Bug Fixes

* resolve FCD Manager CrashLoopBackOff ([#195](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/195)) ([17ad63f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/17ad63f547a2de6f687caa23a4c757057534746e))

## [0.12.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.12.3...idea-shared-v0.12.4) (2026-02-13)


### Bug Fixes

* address PR [#185](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/185) review feedback ([#190](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/190)) ([311fb60](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/311fb6028e14e1341c39eb8b243b27fac344a699))

## [0.12.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.12.2...idea-shared-v0.12.3) (2026-02-13)


### Bug Fixes

* add retry logic for WFS and InfluxDB transient failures ([#185](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/185)) ([347a311](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/347a311fa48fa6a2301932fd09cf3d3ca43d5307))

## [0.12.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.12.1...idea-shared-v0.12.2) (2026-02-13)


### Bug Fixes

* resolve container build and lint workflow issues from uv workspace migration ([#178](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/178)) ([d19f203](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/d19f2030ff67c3c925cdafc1090bd2790b0d5087)), closes [#174](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/174)

## [0.12.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.12.0...idea-shared-v0.12.1) (2026-02-13)


### Bug Fixes

* optimize InfluxDB health check queries with field filters ([#176](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/176)) ([02955a6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/02955a682c65d74a84bf78aff4a8a3cbaf3d23be)), closes [#35](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/35)

## [0.12.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.11.4...idea-shared-v0.12.0) (2026-02-12)


### Bug Fixes

* bound InfluxDB Flux queries to avoid full-shard scans ([#172](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/172)) ([a58787d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/a58787d967438d96fb4e7793e8a0aee0e0ad82fc))

## [0.11.4](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.11.3...idea-shared-v0.11.4) (2026-02-11)


### Miscellaneous Chores

* **idea-shared:** Synchronize idea-helsinki versions

## [0.11.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.11.2...idea-shared-v0.11.3) (2026-02-11)


### Bug Fixes

* increase InfluxDB client timeout from 60s to 300s ([#160](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/160)) ([ce56b8b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/ce56b8b82ac9e3f7e56bab395296556baef1c304))

## [0.11.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.11.1...idea-shared-v0.11.2) (2026-02-05)


### Bug Fixes

* add resilience to segment changelog corruption and graceful shutdown ([#158](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/158)) ([aab7b5e](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/aab7b5e5e617bff55447606ae1cb9414718ee4a9))

## [0.11.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.11.0...idea-shared-v0.11.1) (2026-01-30)


### Bug Fixes

* Sentry error improvements and GoFeatureFlag migration ([#154](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/154)) ([77df5a9](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/77df5a9033aa1a128254327246bcb342178d0c1e))

## [0.11.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.10.0...idea-shared-v0.11.0) (2026-01-29)


### Features

* migrate IDEA-Helsinki to GoFeatureFlag relay proxy ([#149](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/149)) ([c8fcd2e](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c8fcd2eb6323d3e9dca1df36ca7184e6f673df4f))


### Bug Fixes

* **deploy:** correct feature flag env var for fcd-manager multithreading ([#143](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/143)) ([043e26c](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/043e26cbb03e4921f09b9aa837de1b4dbd114810))
* **threading:** use daemon threads for clean process exit ([#150](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/150)) ([9dc277a](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/9dc277ac05d91245ce4c490a018757e34539aeee))

## [0.10.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.9.1...idea-shared-v0.10.0) (2026-01-15)


### Features

* Implement multi-threaded processing for FCD Manager ([#105](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/105)) ([#114](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/114)) ([b90f486](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b90f486659f62f444245379a049329cb6e49a607))

## [0.9.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.6.0...idea-shared-v0.9.1) (2025-11-10)


### Bug Fixes

* **health:** convert PosixPath to string in health check metadata ([#130](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/130)) ([78ebae0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/78ebae051a0791d33fe7656bb347e0d2d579ee10))

## [0.6.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.5.0...idea-shared-v0.6.0) (2025-10-20)


### Features

* implement OpenFeature-based feature flags system ([#118](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/118)) ([ca1d1be](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/ca1d1be14c3ceb0b00d2d28eaa403f921dada71c))

## [0.5.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.4.0...idea-shared-v0.5.0) (2025-10-17)


### Features

* add backfill mode detection to health checks ([#107](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/107)) ([6de35df](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/6de35df21db131c578ee331304ac5980950d9713))

## [0.4.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.3.0...idea-shared-v0.4.0) (2025-10-15)


### Features

* Add comprehensive testing infrastructure with pytest ([#100](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/100)) ([0bb57dd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0bb57dd565d6b9cccefd4d7a09af5ae2ae3baddc))

## [0.3.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.2.3...idea-shared-v0.3.0) (2025-10-10)


### Features

* InfluxDB batching improvements and K8s secrets templating ([#87](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/87)) ([2ae130b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/2ae130b9d62623c9b27f6da634679ab845144812))

## [0.2.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.2.2...idea-shared-v0.2.3) (2025-10-07)


### Bug Fixes

* resolve InfluxDB connection failures ([#63](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/63)) ([bf76a48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/bf76a48b2bb2dce54c164331d61e5d4de6cc1305))

## [0.2.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.2.1...idea-shared-v0.2.2) (2025-10-07)


### Bug Fixes

* trigger service releases for idea-shared 0.2.1 ([#76](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/76)) ([296b85c](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/296b85c507e6861ceac6cd000df50f263425965d))

## [0.2.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.2.0...idea-shared-v0.2.1) (2025-10-07)


### Bug Fixes

* configure DATA_DIR for GCS bucket file storage ([#69](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/69)) ([7eb00bd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/7eb00bd0cda060772343ffd506d5be1c8e7f8adc))

## [0.2.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/idea-shared-v0.1.0...idea-shared-v0.2.0) (2025-10-06)


### Features

* Containerize Python services with modern development workflow ([c20441a](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c20441a493c94af665182ed360685c67cb0053c7))
* Implement health checks for FCD Manager service ([#42](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/42)) ([e3755a6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/e3755a6c4b04c9ca93ba96e7d877fe778e1d42ed))
* Implement health checks for IDEA Helsinki service ([#30](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/30)) ([6fb327f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/6fb327f52e43fc3344a342e8841a8c6155b6b893))
* Implement shared health check module for Kubernetes probes ([#29](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/29)) ([b07650a](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b07650a3512a18a4d276a75bc29529a62c8c962b))
* **traffic-monitor:** implement health checks for Traffic Monitor service ([#43](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/43)) ([187f8f8](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/187f8f85532290a8e875ff11b385057a9fd53751))


### Bug Fixes

* externalize health check configuration constants ([#55](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/55)) ([8b19327](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/8b19327b040d9038ad507904d546cf4e27f415cd))
* **idea-helsinki:** add required parameters to DatabaseHealthCheck initialization ([#48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/48)) ([6ecac59](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/6ecac59193c2376fccc75f2203a53b877e02ff96))
* release-please workspace configuration and dependency tracking ([#64](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/64)) ([fdb1f93](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/fdb1f93c9c5e3ed9edf45126c19730252d795fc2))


### Documentation

* add comprehensive health check documentation ([#58](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/58)) ([6e377b9](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/6e377b9600750c1ca008435a1f58160e93df4f30))
