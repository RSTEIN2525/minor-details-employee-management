# Insert Sample Shop Test
from sqlmodel import Session
from db.session import engine
from models.shop import Shop


def seed_shops():
    with Session(engine) as session:
        # Check if shops already exist to avoid duplicates
        existing_sph = session.get(Shop, "SPH")
        existing_office = session.get(Shop, "OFFICE")
        
        if not existing_sph:
            # Existing SPH shop
            sph_shop = Shop(
                id="SPH",
                name="SPH",
                center_lat=38.9931538759034,
                center_lng= -76.9428334513501,
                radius_meters=100.0,  # 100 m radius
            )
            session.add(sph_shop)
            print("Added SPH shop")
        else:
            print("SPH shop already exists")
        
        if not existing_office:
            # New Office shop
            office_shop = Shop(
                id="OFFICE",
                name="Office",
                center_lat=38.9931538759034,  # Using same coordinates as SPH for now
                center_lng= -76.9428334513501,
                radius_meters=150.0,  # Slightly larger radius for office
            )
            session.add(office_shop)
            print("Added Office shop")
        else:
            print("Office shop already exists")
        
        session.commit()


if __name__ == "__main__":
    seed_shops()

