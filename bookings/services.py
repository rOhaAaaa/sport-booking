from .processors import (
    HallBookingProcessor,
    SessionBookingProcessor,
)


class BookingService:
    @staticmethod
    def create_hall_booking(user, hall_id, starts_at, ends_at):
        processor = HallBookingProcessor()

        return processor.create_booking(
            user,
            {
                "hall_id": hall_id,
                "starts_at": starts_at,
                "ends_at": ends_at,
            },
        )

    @staticmethod
    def create_session_booking(user, session_id):
        processor = SessionBookingProcessor()

        return processor.create_booking(
            user,
            {"session_id": session_id},
        )