"""Eğitmen hesabı açar ya da var olan hesaba ders açma yetkisi verir (ADR-1).

Eğitmen rolü kayıt formundan alınamaz; yönetici bu betiği sunucuda çalıştırır:

    python -m app.scripts.create_instructor --email egitmen@uni.edu.tr --name "Ad Soyad"

Şifre komut satırında verilmez (geçmişe ve süreç listesine düşmesin): INSTRUCTOR_PASSWORD
ortam değişkeninden ya da etkileşimli olarak sorulur.

E-posta doğrulaması olmadığı için var olan bir hesaba yetki ancak --promote-existing ile verilir:
önce hesabın gerçekten o eğitmene ait olduğundan emin olun.

Hesaplardan önce açılmış derslerin eğitmeni yoktur; --course KOD (tekrarlanabilir) hesabı o
derslerin eğitmeni yapar:

    python -m app.scripts.create_instructor --email ... --name "..." --course BLM2512
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password
from app.db.models import Course, Enrollment, User
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--title", default=None, help="Ör. Dr. Öğr. Üyesi")
    parser.add_argument("--promote-existing", action="store_true")
    parser.add_argument("--course", action="append", default=[], help="Eğitmeni olacağı ders kodu")
    args = parser.parse_args()
    email = args.email.strip().lower()

    with SessionLocal() as db:
        courses = []
        for code in args.course:
            course = db.scalar(select(Course).where(Course.code == "".join(code.split()).upper()))
            if course is None:
                sys.exit(f"{code} kodlu ders yok")
            courses.append(course)
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            if not args.promote_existing:
                sys.exit(
                    f"{email} zaten kayıtlı. Hesabın bu eğitmene ait olduğundan eminseniz "
                    "--promote-existing ile yeniden çalıştırın."
                )
            user.can_create_courses = True
            print(f"{email}: ders açma yetkisi verildi (şifre değişmedi)")
        else:
            password = os.environ.get("INSTRUCTOR_PASSWORD") or getpass.getpass("Şifre: ")
            if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
                sys.exit(f"Şifre {MIN_PASSWORD_LENGTH}–{MAX_PASSWORD_LENGTH} karakter olmalı")
            user = User(
                name=args.name.strip(),
                email=email,
                title=args.title,
                password_hash=hash_password(password),
                can_create_courses=True,
            )
            db.add(user)
            db.flush()
            print(f"Eğitmen hesabı oluşturuldu: {email}")
        for course in courses:
            enrollment = db.scalar(
                select(Enrollment).where(
                    Enrollment.user_id == user.id, Enrollment.course_id == course.id
                )
            )
            if enrollment is None:
                db.add(Enrollment(user_id=user.id, course_id=course.id, role="instructor"))
            else:
                enrollment.role = "instructor"
            print(f"{email}: {course.code} dersinin eğitmeni")
        db.commit()


if __name__ == "__main__":
    main()
