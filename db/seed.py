# Insert Sample Shop Test
from db.session import get_session
from models.shop import Shop

def seed_shops():
    session = get_session()
    shop = Shop(
        id="Bill Currie Ford",
        name="Bill Currie Ford",
        center_lat=28.001096072680863,
        center_lng=-82.50458353362974,
        radius_meters=100.0  # 100 m radius
    )
    session.add(shop)
    session.commit()
    session.close()

if __name__ == "__main__":
    seed_shops()
