# IDMA 버전 관리

대개편·릴리즈로 버전을 올리거나 새 로컬 저장소에서 pre-commit 훅을 켤 때 읽는다. patch는 훅이 자동으로 올린다.

- Version lives in `VERSION` as `x.y.z`.
- Patch (z): `scripts/hooks/pre-commit` adds 1 on every commit. Never bump it by hand.
- Minor (y, reset z to 0): bump by hand for a major rework (feature addition, structural refactor).
- Major (x, reset y and z): bump by hand only when the user orders a release.
- The hook leaves patch alone when the commit already raised minor or major against `HEAD`.
- Enable once per local clone (Git does not follow hook paths automatically): `git config core.hooksPath scripts/hooks`.
