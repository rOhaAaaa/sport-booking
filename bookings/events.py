from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class BookingConfirmedEvent:
    booking_id: int


class BookingObserver(ABC):
    @abstractmethod
    def update(self, event):
        pass


class BookingEventPublisher:
    def __init__(self):
        self._observers = []

    def subscribe(self, observer):
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer):
        if observer in self._observers:
            self._observers.remove(observer)

    def notify(self, event):
        for observer in tuple(self._observers):
            observer.update(event)