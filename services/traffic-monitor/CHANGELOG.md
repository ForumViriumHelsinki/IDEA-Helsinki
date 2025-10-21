# Changelog

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
