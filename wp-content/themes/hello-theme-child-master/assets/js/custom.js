/* =========================================
   CITYCOM IN NUMBERS
   ========================================= */

   (function(){
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function formatNumber(n){
    return Math.round(n).toLocaleString('en-GB');
  }

  function animateCount(el){
    var target = parseFloat(el.getAttribute('data-count-to'), 10) || 0;
    var prefix = el.getAttribute('data-prefix') || '';
    var suffix = el.getAttribute('data-suffix') || '';
    var duration = 1800;

    if (reduceMotion) {
      el.textContent = prefix + formatNumber(target) + suffix;
      return;
    }

    var startTime = null;

    function easeOutExpo(t){
      return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
    }

    function step(timestamp){
      if (startTime === null) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      var eased = easeOutExpo(progress);
      var current = target * eased;
      el.textContent = prefix + formatNumber(current) + suffix;
      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        el.textContent = prefix + formatNumber(target) + suffix;
      }
    }

    requestAnimationFrame(step);
  }

  var counters = document.querySelectorAll('.stat-count');

  if ('IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if (entry.isIntersecting) {
          animateCount(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.4 });

    counters.forEach(function(el){ observer.observe(el); });
  } else {
    counters.forEach(animateCount);
  }
})();

/* =========================================
   SAFARI DETECTION
   ========================================= */

(function () {

  var userAgent = navigator.userAgent;

  var isSafari =
    /Safari/i.test(userAgent) &&
    !/Chrome|CriOS|Android|EdgiOS|Edg|OPR|Opera|Firefox|FxiOS/i.test(userAgent);

  if (!isSafari) {
    return;
  }

  document.documentElement.classList.add('is-safari');

})();