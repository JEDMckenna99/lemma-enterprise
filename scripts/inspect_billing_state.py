"""One-off: print platform billing + customer rows (Heroku or local)."""
from api.database import SessionLocal, Customer, PlatformUser, Site

OWNER_PPID = "did:lemma:ppid_005c4e4702198ea53abb28f49a4e370b175ac2f1b34d6018c0615f9a90320de7"


def main() -> None:
    db = SessionLocal()
    try:
        user = db.query(PlatformUser).filter_by(user_did=OWNER_PPID).first()
        if user:
            print(
                "platform_user",
                user.user_did[:40],
                "billing_customer_id=",
                user.billing_customer_id,
                "email=",
                user.email,
            )
        else:
            print("platform_user: not found")

        for c in db.query(Customer).all():
            print(
                "customer",
                c.customer_id,
                c.email,
                c.stripe_customer_id,
                c.subscription_status,
            )

        for s in db.query(Site).filter(Site.site_domain.in_(["lemma.id", "lemma.id"])).all():
            print("site", s.site_id, s.site_domain, s.admin_email)
    finally:
        db.close()


if __name__ == "__main__":
    main()
