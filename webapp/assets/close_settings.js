document.addEventListener('DOMContentLoaded', function () {
  function handleOutsideClick(event) {
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
