/**
 * Board page: sync, queue add/remove/note, other-PRs toggle, drag-and-drop reorder.
 */
(function () {
  "use strict";

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    });
  }

  function parseJsonResponse(res) {
    return res.json().then(function (data) {
      return { ok: res.ok, data: data };
    });
  }

  // Sync button
  var syncBtn = document.getElementById("sync-btn");
  if (syncBtn) {
    syncBtn.addEventListener("click", function () {
      syncBtn.disabled = true;
      syncBtn.textContent = "Syncing…";
      fetch("/api/sync", {
        method: "POST",
        headers: { Accept: "application/json" },
      })
        .then(parseJsonResponse)
        .then(function (result) {
          if (result.ok) {
            window.location.reload();
          } else {
            syncBtn.disabled = false;
            syncBtn.textContent = "Sync now";
            alert(result.data.error || "Sync failed");
          }
        })
        .catch(function (err) {
          syncBtn.disabled = false;
          syncBtn.textContent = "Sync now";
          alert("Sync failed: " + (err.message || "network error"));
        });
    });
  }

  // Poll last-sync so the label updates after background sync (no reload)
  var lastSyncLabel = document.getElementById("last-sync-label");
  if (lastSyncLabel) {
    var POLL_INTERVAL_MS = 60 * 1000; // 1 minute
    function updateLastSyncLabel() {
      fetch("/api/last-sync", { headers: { Accept: "application/json" } })
        .then(parseJsonResponse)
        .then(function (result) {
          if (result.ok && result.data && result.data.last_sync) {
            var iso = result.data.last_sync;
            var d = new Date(iso);
            if (!isNaN(d.getTime())) {
              var formatted =
                d.getUTCFullYear() +
                "-" +
                String(d.getUTCMonth() + 1).padStart(2, "0") +
                "-" +
                String(d.getUTCDate()).padStart(2, "0") +
                " " +
                String(d.getUTCHours()).padStart(2, "0") +
                ":" +
                String(d.getUTCMinutes()).padStart(2, "0") +
                " UTC";
              lastSyncLabel.textContent = "Last sync: " + formatted;
            }
          } else if (result.ok && result.data && result.data.last_sync === null) {
            lastSyncLabel.textContent = "No PRs cached — click Sync now.";
          }
        })
        .catch(function () {});
    }
    setInterval(updateLastSyncLabel, POLL_INTERVAL_MS);
    setTimeout(updateLastSyncLabel, 5000); // refresh once soon after load
  }

  // Add to queue
  document.querySelectorAll(".queue-add").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var prNumber = parseInt(btn.getAttribute("data-pr-number"), 10);
      postJson("/api/queue/add", { pr_number: prNumber })
        .then(parseJsonResponse)
        .then(function (result) {
          if (result.ok) {
            window.location.reload();
          } else {
            alert(result.data.error || "Failed to add to queue");
          }
        })
        .catch(function (err) {
          alert("Failed: " + (err.message || "network error"));
        });
    });
  });

  // Remove from queue
  document.querySelectorAll(".queue-remove").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var prNumber = parseInt(btn.getAttribute("data-pr-number"), 10);
      postJson("/api/queue/remove", { pr_number: prNumber })
        .then(parseJsonResponse)
        .then(function (result) {
          if (result.ok) {
            window.location.reload();
          } else {
            alert(result.data.error || "Failed to remove");
          }
        })
        .catch(function (err) {
          alert("Failed: " + (err.message || "network error"));
        });
    });
  });

  // Save note
  document.querySelectorAll(".queue-note-save").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var row = btn.closest("tr");
      var prNumber = parseInt(row.getAttribute("data-pr-number"), 10);
      var input = row.querySelector(".queue-note-input");
      var note = input ? input.value : "";
      postJson("/api/queue/note", { pr_number: prNumber, note: note })
        .then(parseJsonResponse)
        .then(function (result) {
          if (result.ok) {
            window.location.reload();
          } else {
            alert(result.data.error || "Failed to save note");
          }
        })
        .catch(function (err) {
          alert("Failed: " + (err.message || "network error"));
        });
    });
  });

  // Other PRs toggle (preserve initial label from server-rendered text)
  var otherToggle = document.getElementById("other-prs-toggle");
  var otherSection = document.getElementById("other-prs-section");
  var otherLabel = document.getElementById("other-prs-toggle-label");
  var otherChevron = document.getElementById("other-prs-chevron");
  var initialOtherLabel = otherLabel ? otherLabel.textContent : "Show other PRs (0)";
  if (otherToggle && otherSection) {
    otherToggle.addEventListener("click", function () {
      var isHidden = otherSection.classList.contains("hidden");
      otherSection.classList.toggle("hidden");
      if (otherLabel) {
        otherLabel.textContent = isHidden ? "Hide other PRs" : initialOtherLabel;
      }
      if (otherChevron) {
        otherChevron.textContent = isHidden ? "▲" : "▼";
      }
    });
  }

  // Drag-and-drop reorder (SortableJS)
  var queueTbody = document.getElementById("queue-tbody");
  if (queueTbody && typeof Sortable !== "undefined") {
    Sortable.create(queueTbody, {
      animation: 150,
      handle: ".drag-handle",
      onEnd: function () {
        var rows = queueTbody.querySelectorAll("tr");
        var orderedPrNumbers = [];
        for (var i = 0; i < rows.length; i++) {
          var prNum = parseInt(rows[i].dataset.prNumber, 10);
          if (!isNaN(prNum)) {
            orderedPrNumbers.push(prNum);
          }
        }
        postJson("/api/queue/reorder", {
          ordered_pr_numbers: orderedPrNumbers,
        })
          .then(parseJsonResponse)
          .then(function (result) {
            if (result.ok) {
              window.location.reload();
            } else {
              alert(result.data.error || "Reorder failed");
            }
          })
          .catch(function (err) {
            alert("Reorder failed: " + (err.message || "network error"));
          });
      },
    });
  }
})();
