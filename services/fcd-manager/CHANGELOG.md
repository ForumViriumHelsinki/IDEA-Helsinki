# Changelog

## [0.10.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.9.1...fcd-manager-v0.10.0) (2026-01-15)


### Features

* **health:** add startup-specific health checks to fcd-manager ([#138](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/138)) ([0ffb69b](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0ffb69bacf5b766b7d19e8263a3d71b5e6435233)), closes [#137](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/137)
* **health:** add startup-specific health checks to orchestrator service ([#140](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/140)) ([3f29264](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/3f292640ea3e1e5e84f2a8e141d24a733d0113bd))
* **health:** add startup-specific health checks to traffic-monitor service ([#141](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/141)) ([0d33a6f](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0d33a6f7bf8d34ef0f558aa9478cf9400d6850a0))
* Implement multi-threaded processing for FCD Manager ([#105](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/105)) ([#114](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/114)) ([b90f486](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b90f486659f62f444245379a049329cb6e49a607))

## [0.9.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.9.0...fcd-manager-v0.9.1) (2025-11-10)


### Bug Fixes

* **health:** convert PosixPath to string in health check metadata ([#130](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/130)) ([78ebae0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/78ebae051a0791d33fe7656bb347e0d2d579ee10))

## [0.9.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.6.2...fcd-manager-v0.9.0) (2025-10-24)


### Miscellaneous Chores

* **fcd-manager:** Synchronize idea-helsinki-services versions

## [0.6.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.6.1...fcd-manager-v0.6.2) (2025-10-21)


### Bug Fixes

* **services:** update for idea-shared module changes ([#121](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/121)) ([26039d3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/26039d32ec5b4244635272628054742bba85afea))

## [0.6.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.6.0...fcd-manager-v0.6.1) (2025-10-20)


### Bug Fixes

* add pytest asyncio_mode configuration to prevent test hangs ([#120](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/120)) ([260b1bf](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/260b1bf038705ddb496eea8ee96160b98e48c1e0)), closes [#119](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/119)

## [0.6.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.5.0...fcd-manager-v0.6.0) (2025-10-20)


### Features

* adjust Sentry SDK sample rate to 0.1 for quota management ([#112](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/112)) ([840072d](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/840072dfb60c1bc55b623b2a466b060fceda0155)), closes [#111](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/111)

## [0.5.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.4.2...fcd-manager-v0.5.0) (2025-10-15)


### Features

* Add comprehensive testing infrastructure with pytest ([#100](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/100)) ([0bb57dd](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/0bb57dd565d6b9cccefd4d7a09af5ae2ae3baddc))

## [0.4.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.4.1...fcd-manager-v0.4.2) (2025-10-10)


### Bug Fixes

* **services:** update for idea-shared module changes ([#94](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/94)) ([1ac1981](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/1ac1981d648068b1aba14478024d07cf06756509))

## [0.4.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.4.0...fcd-manager-v0.4.1) (2025-10-08)


### Bug Fixes

* remove version pinning for idea-shared in services ([#85](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/85)) ([b2ab907](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/b2ab9072f719a807d5c143857b069b0c42733352))

## [0.4.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.3.3...fcd-manager-v0.4.0) (2025-10-08)


### Features

* configure Sentry for all IDEA-Helsinki services ([#80](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/80)) ([ec99d37](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/ec99d37366625d15e9419c0190978b9e4f32907a)), closes [#79](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/79)

## [0.3.3](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.3.2...fcd-manager-v0.3.3) (2025-10-07)


### Bug Fixes

* trigger service releases for idea-shared 0.2.1 ([#76](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/76)) ([296b85c](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/296b85c507e6861ceac6cd000df50f263425965d))

## [0.3.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.3.1...fcd-manager-v0.3.2) (2025-10-06)


### Bug Fixes

* release-please workspace configuration and dependency tracking ([#64](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/64)) ([fdb1f93](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/fdb1f93c9c5e3ed9edf45126c19730252d795fc2))

## [0.3.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.3.0...fcd-manager-v0.3.1) (2025-10-01)


### Bug Fixes

* replace SEGMENT_MAPPING_MAX_AGE_MINUTES with FCD_MAPPING_MAX_AGE_MINUTES ([#45](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/45)) ([e296166](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/e2961667db9b016888b236249138ec1971967684)), closes [#44](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/44)

## [0.3.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.2.2...fcd-manager-v0.3.0) (2025-09-30)


### Features

* Implement health checks for FCD Manager service ([#42](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/42)) ([e3755a6](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/e3755a6c4b04c9ca93ba96e7d877fe778e1d42ed))

## [0.2.2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.2.1...fcd-manager-v0.2.2) (2025-09-08)


### Bug Fixes

* resolve Docker build context issues for all services ([#20](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/20)) ([d246ad2](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/d246ad288136f9fd8c05aa5a3835503dd2ce8f7b))

## [0.2.1](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.2.0...fcd-manager-v0.2.1) (2025-09-08)


### Bug Fixes

* correct Docker build context paths for GitHub Actions ([#18](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/18)) ([86b6f48](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/86b6f48f6229cc32eef156b274f1a88fbb33443f))

## [0.2.0](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/compare/fcd-manager-v0.1.0...fcd-manager-v0.2.0) (2025-09-04)


### Features

* Containerize Python services with modern development workflow ([c20441a](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/commit/c20441a493c94af665182ed360685c67cb0053c7))
