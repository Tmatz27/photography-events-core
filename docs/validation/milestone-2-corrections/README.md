# Required S1 correction code-freeze evidence

Unedited artifact11390387262 from [run37414083448](https://github.com/Tmatz27/photography-events-core/actions/runs/37414083448), SHA49d95d43f31626f3c6a60e0a272ab6d1a6081678. ZIP SHA-256 verified:2a5d7037d56c16e6154f5835db59e827364af83716ab95b3f9f6228d5a4db05b.

[CI receipt](ci.json), [pytest log](pytest.log), [JUnit](tests.xml),
[legacy parity](parity.json), [container/migration/backup/restore acceptance](acceptance.json),
[frozen DB](frozen-database.json), [M1/shadow measurements and full plans](m2-performance.json).

218 tests pass, including all38 A-scenarios and eight S1 tests.
M1 timing is measured independently from explicit shadow drain. These are warm
synthetic fixture measurements, not production SLAs. Final documentation
commit/CI receipts are outside the repository to avoid a self-hash cycle.
