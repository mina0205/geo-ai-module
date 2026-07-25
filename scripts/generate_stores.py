"""가상 점포 생성기 (Day 2).

업종 10개(요식업 비중 높음) × 서울 동네 × 특징·가격·영업시간 조합으로
가짜 점포 프로필을 생성한다. 리뷰 요약은 약 60%를 '없음'으로 만든다
(configs/task_templates.json 의 review_policy 참조).

사용:
    python scripts/generate_stores.py --count 120 --seed 42
    → data/synthetic/stores.jsonl
"""

import argparse
import json
import random
from pathlib import Path

OUT_DEFAULT = Path(__file__).parent.parent / "data" / "synthetic" / "stores.jsonl"

NO_REVIEW_RATIO = 0.6

# 서울 프로젝트 기준 — 블로그 SEO에서 지역 키워드가 동네 단위로 쓰이므로 동 수준까지 표기
LOCATIONS = [
    "서울 마포구 망원동", "서울 마포구 연남동", "서울 마포구 합정동",
    "서울 성동구 성수동", "서울 중구 을지로3가", "서울 종로구 익선동",
    "서울 종로구 서촌", "서울 영등포구 문래동", "서울 송파구 송리단길",
    "서울 관악구 샤로수길", "서울 동대문구 회기동", "서울 광진구 건대입구",
    "서울 서대문구 연희동", "서울 용산구 해방촌", "서울 강북구 수유동",
    "서울 은평구 연신내", "서울 강서구 마곡동", "서울 노원구 공릉동",
]

CLOSED = ["월요일 휴무", "화요일 휴무", "일요일 휴무", "연중무휴", "매주 첫째·셋째 월요일 휴무"]

# 업종 10개. weight 합 100 — 요식업 5개가 64%
CATEGORIES = {
    "카페": {
        "weight": 16,
        "names": ["카페 {w}", "{w}커피", "커피집 {w}", "{w} 로스터스"],
        "words": ["온도", "달문", "모퉁이", "소소", "초록", "오후", "물결", "숲", "구름", "여백", "윤슬", "브라운", "한적", "새벽"],
        "hours": ["매일 10:00~22:00", "평일 09:00~21:00 / 주말 11:00~22:00", "매일 08:30~20:00"],
        "menus": [("아메리카노", 4500), ("카페라떼", 5000), ("아인슈페너", 6000), ("말차라떼", 5500),
                  ("바스크 치즈케이크", 6500), ("크루아상", 4000), ("스콘", 3800)],
        "features": ["직접 로스팅한 원두 사용", "1인석과 콘센트 좌석 많음", "노키즈존 아님(아기의자 있음)",
                     "테라스 좌석 4개", "디저트 매일 직접 굽음", "반려동물 동반 가능", "화이트톤 인테리어로 사진 찍기 좋음"],
        "reviews": ["커피가 산미 없이 고소하다는 평이 많음", "조용해서 작업하기 좋다는 후기가 많음",
                    "{menu}가 시그니처로 자주 언급됨"],
    },
    "한식당": {
        "weight": 14,
        "names": ["{w}밥상", "{w}식당", "{w} 한상", "밥집 {w}"],
        "words": ["시골", "온기", "정든", "골목", "할머니", "든든", "솥", "푸른", "안골", "백반", "가마솥", "동구밭", "해온", "누리"],
        "hours": ["매일 11:00~21:00 (브레이크 15:00~17:00)", "평일 11:00~20:30", "매일 10:30~21:30"],
        "menus": [("김치찌개", 9000), ("된장찌개", 9000), ("제육볶음", 10000), ("불고기정식", 12000),
                  ("청국장", 9500), ("고등어구이 정식", 11000)],
        "features": ["반찬 6종 셀프바 무한 리필", "매일 아침 직접 담근 겉절이", "혼밥 좌석 있음",
                     "점심 직장인 손님 많음", "공기밥 무료 추가", "단체석(12인) 예약 가능"],
        "reviews": ["집밥 같다는 평이 많음", "{menu}가 맛집으로 소문남", "반찬이 정갈하다는 후기 다수"],
    },
    "분식집": {
        "weight": 12,
        "names": ["{w}분식", "{w} 떡볶이", "분식왕 {w}", "{w}네 분식"],
        "words": ["오동통", "골목", "빨간", "추억", "동네", "매콤", "옛날", "방앗간", "단짝", "별별", "호호", "통통"],
        "hours": ["매일 10:00~20:00", "평일 09:00~19:00 / 토 10:00~18:00", "매일 11:00~21:00"],
        "menus": [("떡볶이", 4500), ("치즈떡볶이", 6000), ("김밥", 3500), ("참치김밥", 4500),
                  ("튀김 모둠", 5000), ("순대", 5000), ("라볶이", 6500)],
        "features": ["떡은 매일 아침 방앗간에서 받아옴", "포장 시 1,000원 할인", "국물떡볶이·기름떡볶이 선택 가능",
                     "매운맛 3단계 조절", "배달 가능(배달앱 입점)", "테이블 4개의 작은 가게"],
        "reviews": ["{menu} 양이 많다는 평", "학생 단골이 많음", "튀김이 항상 갓 튀겨 나온다는 후기"],
    },
    "치킨·호프": {
        "weight": 12,
        "names": ["{w}치킨", "{w} 펍", "치킨하우스 {w}", "{w} 호프"],
        "words": ["바삭", "노을", "골목대장", "동네", "심야", "장작", "호수", "황금", "포차", "광장", "펄펄", "곰"],
        "hours": ["매일 16:00~01:00", "매일 17:00~02:00", "화~일 16:30~24:00"],
        "menus": [("후라이드 치킨", 19000), ("양념치킨", 20000), ("반반치킨", 20000), ("마늘간장치킨", 21000),
                  ("생맥주 500cc", 4500), ("감자튀김", 8000)],
        "features": ["국내산 냉장육만 사용", "주문 즉시 조리(15~20분)", "심야 포장 주문 많음",
                     "스포츠 중계 대형 TV 2대", "2층 단체석 있음", "무뼈 옵션 가능"],
        "reviews": ["튀김옷이 얇고 바삭하다는 평", "{menu} 재주문율이 높음", "사장님이 친절하다는 후기 다수"],
    },
    "베이커리": {
        "weight": 10,
        "names": ["{w} 베이커리", "빵집 {w}", "{w} 브레드", "오븐 {w}"],
        "words": ["아침", "밀밭", "버터", "화덕", "느린", "결", "반죽", "효모", "햇살", "크럼", "도톰", "온화"],
        "hours": ["매일 08:00~20:00", "화~일 07:30~19:00", "매일 09:00~21:00 (당일 소진 시 조기 마감)"],
        "menus": [("소금빵", 3500), ("크림빵", 3800), ("바게트", 4500), ("식빵", 5500),
                  ("단팥빵", 3000), ("치아바타", 4000)],
        "features": ["천연발효종 사용", "하루 2회(오전 8시·오후 2시) 갓 구운 빵 나옴", "비건 옵션 일부 있음",
                     "당일 생산 당일 판매 원칙", "케이크 예약 주문 가능", "선물 포장 무료"],
        "reviews": ["{menu}는 오후에 가면 품절이라는 후기 다수", "빵이 무겁지 않고 담백하다는 평", "재료가 좋다는 평이 많음"],
    },
    "미용실": {
        "weight": 8,
        "names": ["헤어 {w}", "{w} 살롱", "살롱 드 {w}", "{w} 헤어스튜디오"],
        "words": ["모리", "블랑", "윤", "결", "숨", "라운", "채", "세연", "무화", "리프", "단정", "온"],
        "hours": ["화~일 10:00~20:00", "매일 10:30~19:30 (예약 우선)", "수~월 10:00~21:00"],
        "menus": [("여성 커트", 25000), ("남성 커트", 18000), ("뿌리염색", 60000), ("펌", 90000),
                  ("클리닉", 50000)],
        "features": ["1인 원장 단독 시술", "네이버 예약 가능", "두피 진단 무료",
                     "애쉬 계열 염색 전문", "첫 방문 10% 할인", "조용한 매장(수다 부담 없음)"],
        "reviews": ["상담이 꼼꼼하다는 평", "{menu} 후 손질이 편하다는 후기", "재방문율이 높다는 평"],
    },
    "네일샵": {
        "weight": 7,
        "names": ["네일 {w}", "{w} 네일바", "{w}네일", "아뜰리에 {w}"],
        "words": ["봄", "무드", "제나", "은하", "결", "블룸", "달로", "셀렌", "라뮤", "포근", "윤월"],
        "hours": ["매일 11:00~21:00 (예약제)", "화~일 10:30~20:00", "매일 12:00~22:00"],
        "menus": [("젤 원컬러", 35000), ("젤 아트", 55000), ("패디 원컬러", 45000), ("케어", 20000),
                  ("젤 제거", 10000)],
        "features": ["100% 예약제", "1인샵(원장 단독)", "이달의 아트 시즌 디자인 운영",
                     "타샵 제거 무료", "주차 1대 가능", "인스타 디자인 포트폴리오 운영"],
        "reviews": ["아트가 섬세하다는 평", "유지력이 좋다는 후기 다수", "상담이 편하다는 평"],
    },
    "헬스장": {
        "weight": 7,
        "names": ["{w} 짐", "{w} 피트니스", "짐 {w}", "{w} 트레이닝"],
        "words": ["철", "번", "라이언", "온", "그릿", "스파크", "파워", "리프트", "비스트", "불꽃", "단단"],
        "hours": ["평일 06:00~23:00 / 주말 09:00~18:00", "연중무휴 24시간", "평일 06:30~22:30"],
        "menus": [("1개월권", 60000), ("3개월권", 150000), ("PT 10회", 550000), ("일일권", 10000),
                  ("운동복·수건 대여(월)", 20000)],
        "features": ["프리웨이트존 넓음", "머신 최신 기종", "샤워실·개인 락커 완비",
                     "PT 전문(바디프로필 준비반 운영)", "혼잡 시간대 안내 서비스", "주차 지원"],
        "reviews": ["기구 관리가 잘된다는 평", "트레이너가 자세를 꼼꼼히 잡아준다는 후기", "쾌적하다는 평이 많음"],
    },
    "꽃집": {
        "weight": 7,
        "names": ["플라워 {w}", "{w} 꽃집", "{w} 플레르", "꽃방 {w}"],
        "words": ["오월", "숨", "조각", "달", "여름", "안개", "목화", "작약", "바람", "윤슬", "들"],
        "hours": ["매일 10:00~20:00", "화~일 11:00~19:00", "평일 10:00~21:00 / 주말 예약제"],
        "menus": [("미니 꽃다발", 15000), ("꽃다발(중)", 30000), ("꽃바구니", 50000), ("화분(중형)", 25000),
                  ("월 구독(2회 배송)", 45000)],
        "features": ["당일 아침 경매 꽃 사용", "무료 메시지 카드", "꽃 구독 서비스 운영",
                     "화분 분갈이 서비스", "예약 시 픽업 시간 지정 가능", "근처 배달 가능(2km 이내)"],
        "reviews": ["꽃이 오래간다는 평", "포장이 예쁘다는 후기 다수", "{menu} 구성이 알차다는 평"],
    },
    "세탁소": {
        "weight": 7,
        "names": ["{w} 세탁소", "{w} 클리닝", "세탁명가 {w}", "{w} 런드리"],
        "words": ["새하얀", "정직", "우리동네", "손", "맑음", "반짝", "다림", "백년", "포근", "새봄"],
        "hours": ["평일 08:00~20:00 / 토 09:00~18:00", "매일 08:30~20:30 (일요일 휴무)", "평일 07:30~21:00"],
        "menus": [("와이셔츠", 2500), ("정장 상하", 9000), ("코트", 12000), ("패딩", 15000),
                  ("이불(싱글)", 15000), ("운동화 세탁", 10000)],
        "features": ["30년 경력 사장님 직접 세탁", "수선 가능(밑단·지퍼)", "당일 급세탁 가능(오전 접수분)",
                     "무인 보관함 픽업 서비스", "명품 의류 특수 세탁", "정기 고객 적립 할인"],
        "reviews": ["얼룩 제거를 잘한다는 평", "꼼꼼하고 정직하다는 후기 다수", "수선 마감이 깔끔하다는 평"],
    },
}


def pick_category(rng: random.Random) -> str:
    names = list(CATEGORIES)
    weights = [CATEGORIES[c]["weight"] for c in names]
    return rng.choices(names, weights=weights, k=1)[0]


def make_store(rng: random.Random, idx: int, used_names: set, has_review: bool) -> dict:
    category = pick_category(rng)
    spec = CATEGORIES[category]

    name = None
    for _ in range(20):
        cand = rng.choice(spec["names"]).format(w=rng.choice(spec["words"]))
        if cand not in used_names:
            name = cand
            break
    if name is None:  # 조합 고갈 시 지점명으로 구분
        name = f"{cand} {rng.choice(['본점', '2호점', '별관'])}"
    used_names.add(name)

    menus = rng.sample(spec["menus"], k=rng.randint(2, 3))
    menu_str = ", ".join(f"{m} {p:,}원" for m, p in menus)
    prices = [p for _, p in menus]
    price_range = f"{min(prices):,}~{max(prices):,}원" if min(prices) != max(prices) else f"{prices[0]:,}원"

    features = rng.sample(spec["features"], k=rng.randint(2, 4))
    features_str = f"대표메뉴: {menu_str} / " + ", ".join(features)

    hours = f"{rng.choice(spec['hours'])} ({rng.choice(CLOSED)})"

    if has_review:
        review = rng.choice(spec["reviews"]).format(menu=menus[0][0])
    else:
        review = "없음"

    return {
        "store_id": f"store_{idx:04d}",
        "store_name": name,
        "category": category,
        "location": rng.choice(LOCATIONS),
        "hours": hours,
        "price_range": price_range,
        "features": features_str,
        "review_summary": review,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    used_names: set = set()
    # 리뷰 없음 비율을 확률이 아니라 정확한 개수로 보장 (약 60%)
    n_no_review = round(args.count * NO_REVIEW_RATIO)
    review_flags = [False] * n_no_review + [True] * (args.count - n_no_review)
    rng.shuffle(review_flags)
    stores = [make_store(rng, i + 1, used_names, review_flags[i]) for i in range(args.count)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for s in stores:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    no_review = sum(1 for s in stores if s["review_summary"] == "없음")
    by_cat: dict = {}
    for s in stores:
        by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1
    print(f"{len(stores)}개 점포 생성 → {args.out}")
    print(f"리뷰 없음 비율: {no_review}/{len(stores)} ({no_review / len(stores):.0%})")
    print("업종 분포:", dict(sorted(by_cat.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
