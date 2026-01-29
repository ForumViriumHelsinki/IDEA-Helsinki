# Changelog

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
