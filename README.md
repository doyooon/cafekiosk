## ☕️ 카페 주문 키오스크용 챗봇
  

## ❓환경 설치  
- **OS** : Ubuntu 20.04.6 LTS 
- **아나콘다** : Anaconda ver. 24.1.2
- **환경** : Python 3.7.9
- **RASA** : Rasa 2.8.27
### 💻 anaconda 환경 및 관련 패키지 설치 방법

---

1. anaconda 환경 설치 및 **활성화**
```python
conda create –n 가상환경이름 python==3.7.9
conda activate 가상환경이름
```
2. pip 업데이트 및 Rasa 설치
```python
pip install -U pip setuptools wheel
pip install rasa==2.8.27
```
3. spacy 설치 및 spacy한국어 모델 설치
```python
pip install spacy
python -m spacy download ko_core_news_sm
```
4. konlpy 한국어 형태소 분석기 설치
```python
pip install konlpy
```
5. **로컬환경에 Mecab 설치 필요** : 참고(https://malin.tistory.com/60)
```python
pip install mecab-python3
```
6. **custom tokenizer 적용**

      1. git에 있는 **custom_tokenizer.py** 다운로드
      2. anaconda3/envs/환경이름/lib/python3.7/site-packages/rasa/nlu/tokenizers/ 경로에 위 파일 추가
      3. anaconda3/envs/환경이름/lib/python3.7/site-packages/rasa/nlu/registry.py에 custom_tokenizer import 및 componet_classes에 custom_tokenizer 클래스 추가


---
## ▶️ 실행 방법
터미널 2개를 열어 다음 과정을 반복
1. git의 rasa폴더를 다운받은 위치로 이동
2. rasa 및 관련 패키치가 설치된   아나콘다 환경 activate

- **1 번 터미널 (챗봇)**
  ```python
  rasa shell # -vv 옵션 : 디버깅
  ```
- **2번 터미널 (action - 서비스 처리)**
  ```python
  rasa run actions
  ```
