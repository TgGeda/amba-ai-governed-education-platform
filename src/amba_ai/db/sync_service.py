from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class LibrarySyncService(FileSystemEventHandler):
    def __init__(self, path, on_change):
        self.path = path
        self.on_change = on_change
        self.observer = Observer()

    def on_any_event(self, event):
        if not event.is_directory:
            self.on_change()

    def start(self):
        self.observer.schedule(self, self.path, recursive=False)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()