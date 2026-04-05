// js/notifications.js
document.addEventListener('DOMContentLoaded', async () => {
    // Check if notifications are supported
    if (!("Notification" in window)) {
        console.log("This browser does not support desktop notification");
        return;
    }

    // Register Service Worker
    if ('serviceWorker' in navigator) {
        try {
            const registration = await navigator.serviceWorker.register('/sw.js');
            console.log('Service Worker registered with scope:', registration.scope);
            
            // Request Notification Permission
            if (Notification.permission === 'default' || Notification.permission === 'prompt') {
                const permission = await Notification.requestPermission();
                console.log('Notification permission:', permission);
            }

            const user = localStorage.getItem('user') || sessionStorage.getItem("user");
            if (user && Notification.permission === 'granted') {
                // Poll backend for proximity missions every 15 seconds
                setInterval(async () => {
                   try {
                       const res = await fetch(`${window.location.origin}/notifications/poll?email=${user}`);
                       if(res.ok) {
                           const data = await res.json();
                           if (data.notifications && data.notifications.length > 0) {
                               let notified = JSON.parse(sessionStorage.getItem('notified_missions') || '[]');
                               data.notifications.forEach(m => {
                                   if (!notified.includes(m.id)) {
                                       registration.showNotification("New Mission Nearby! 🌍", {
                                           body: `${m.type} reported near you. Open Dashboard to inspect.`,
                                           icon: "https://cdn-icons-png.flaticon.com/512/3233/3233483.png"
                                       });
                                       notified.push(m.id);
                                   }
                               });
                               sessionStorage.setItem('notified_missions', JSON.stringify(notified));
                           }
                       }
                   } catch(e) {
                       console.error("Polling error", e);
                   }
                }, 15000);

                // Poll backend for proximity verifications every 20 seconds
                setInterval(async () => {
                   try {
                       const vRes = await fetch(`${window.location.origin}/notifications/verify_poll?email=${user}`);
                       if(vRes.ok) {
                           const vData = await vRes.json();
                           if (vData.verifications && vData.verifications.length > 0) {
                               let asked = JSON.parse(sessionStorage.getItem('asked_verifications') || '[]');
                               for (let m of vData.verifications) {
                                   if (!asked.includes(m.id)) {
                                       // Trigger Verify Modal if on dashboard
                                       if(window.location.pathname.includes('Dashboard.html') && typeof window.showVerifyModal === 'function') {
                                           window.showVerifyModal(m);
                                           asked.push(m.id);
                                           break; // only ask one at a time
                                       } else {
                                           // Just show push notification
                                           registration.showNotification("Verify nearby mission", {
                                               body: `Are you near ${m.location_text}? Is there garbage? Open Dashboard to confirm.`,
                                               icon: "https://cdn-icons-png.flaticon.com/512/3233/3233483.png"
                                           });
                                           asked.push(m.id);
                                           break;
                                       }
                                   }
                               }
                               sessionStorage.setItem('asked_verifications', JSON.stringify(asked));
                           }
                       }
                   } catch(e) { }
                }, 20000);
            }
        } catch (error) {
            console.error('Service Worker registration failed:', error);
        }
    }
});
