# Insert Sample Shop Test
from db.session import get_session
from models.shop import Shop


def seed_shops():
    session = get_session()
    shop = Shop(
        id="SPH",
        name="SPH",
        center_lat=38.9931538759034,
        center_lng= -76.9428334513501,
        radius_meters=100.0,  # 100 m radius
    )
    session.add(shop)
    session.commit()
    session.close()


if __name__ == "__main__":
    seed_shops()

