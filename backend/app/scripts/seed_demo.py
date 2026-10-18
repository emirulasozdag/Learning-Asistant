"""Demo dersini oluşturur (yoksa). Kullanım: python -m app.scripts.seed_demo"""

from sqlalchemy import select

from app.db.models import Course
from app.db.session import SessionLocal

DEMO_COURSE = {"code": "BLM2512", "name": "Veri Yapıları ve Algoritmalar", "language": "tr"}


def main() -> None:
    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.code == DEMO_COURSE["code"]))
        if course is None:
            course = Course(**DEMO_COURSE)
            db.add(course)
            db.commit()
            print(f"Ders oluşturuldu: {course.code} — {course.name} (id={course.id})")
        else:
            print(f"Ders zaten var: {course.code} (id={course.id})")


if __name__ == "__main__":
    main()
