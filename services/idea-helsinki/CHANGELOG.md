# Changelog

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
