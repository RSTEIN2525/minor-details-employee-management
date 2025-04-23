# Insert Sample Shop Test
from db.session import get_session
from models.shop import Shop


def seed_shops():
    session = get_session()
    shop = Shop(
        id="Startup Shell",
        name="Startup Shell",
        center_lat=99035806837354,
        center_lng=-76.93804041871792,
        radius_meters=100.0,  # 100 m radius
    )
    session.add(shop)
    session.commit()
    session.close()


if __name__ == "__main__":
    seed_shops()

