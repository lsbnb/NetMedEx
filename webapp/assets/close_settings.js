document.addEventListener('DOMContentLoaded', function () {
  function handleOutsideClick(event) {
    var gBtn = document.getElementById('graph-settings-btn');
    var gCollapse = document.getElementById('graph-settings-collapse');
    if (gBtn && gCollapse && gCollapse.style.visibility === 'visible') {
      if (!gCollapse.contains(event.target) && !gBtn.contains(event.target)) {
        gBtn.click();
      }
    }
    var aBtn = document.getElementById('advanced-settings-btn');
    var aCollapse = document.getElementById('advanced-settings-collapse');
    if (aBtn && aCollapse && aCollapse.style.visibility === 'visible') {
      if (!aCollapse.contains(event.target) && !aBtn.contains(event.target)) {
        aBtn.click();
      }
    }
  }
  document.addEventListener('click', handleOutsideClick);
});
