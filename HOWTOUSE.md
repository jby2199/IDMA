# 기본 세팅
 
## VS CODE 상 최초 1회 세팅

### git 업로더 설정
git config --global user.name "JBY"
git config --global user.email "cloud2199@gmail.com"


### VS Code에서 흔히 하는 실수 2개 (미리 방지)
✅ 실수 1: 인터프리터를 .venv로 안 맞춤
- Ctrl+Shift+P
- “Python: Select Interpreter”
- .venv 선택


## 프로젝트 복제 시 1회 세팅


# 템플릿 복제 방식 A

방식 A: 템플릿을 “복사해서 시작” (가장 단순/초보 친화)
1) 폴더 복사
python-project-template/ 폴더를 그대로 복사해서 새 이름으로 변경

2) VS Code에서 새 폴더 열기
VS Code → File > Open Folder... → folder2xlsx/ 선택

3) 가상환경 만들기
터미널에서:
    `python -m venv .venv`

Windows라면:
    `.venv\Scripts\activate`
(※ 파워쉘 실행정책 때문에 막히면: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)

4) 의존성 설치 (필요한 것만)
아직 뭘 만들지 정하지 않았으면 일단 최소만:
    `pip install -U pip`
프로젝트가 정해지면 그때 watchdog, openpyxl 등 추가.

5) Git 새로 시작(템플릿 이력 끊기)
템플릿의 .git 폴더가 남아있으면 지우고 새로 초기화:

    ```
    rm -rf .git
    git init
    git add .
    git commit -m "init: from template"
    Windows 탐색기에서 .git 폴더 삭제해도 됨.
    ```

## ✅ 이 방식 장점
- 생각할 게 없음
- “템플릿 폴더 하나 = 프로젝트 하나”로 명확



# 템플릿 복제 방식 B
방식 B: 템플릿을 “Git 템플릿 리포지토리”로 운영 (팀/여러 프로젝트에 최적)
템플릿을 앞으로 계속 재사용할 거면 이게 제일 깔끔함.

1) 템플릿을 별도 Git repo로 만든다
예: python-template 저장소

2) 새 프로젝트 만들 때는 Use this template(GitHub) / 또는 clone 후 rename
로컬만 쓸 거면:

git clone <template-repo-url> folder2xlsx
cd folder2xlsx
rm -rf .git
git init
git add .
git commit -m "init: from template"

## ✅ 이 방식 장점

- 템플릿 개선이 계속 누적됨
- 팀원이 있어도 동일한 시작점 제공