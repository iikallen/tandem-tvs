self.addEventListener("push", (event) => {
  event.waitUntil(
    self.registration.showNotification("Tandem Portal", {
      tag: "tandem-update",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow("/notifications"));
});
