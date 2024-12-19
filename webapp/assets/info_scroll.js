// document.addEventListener("DOMContentLoaded", () => {setTimeout(() => {
//   const headerFixedHolder = document.querySelector(".sidebar")
//   const headerFixedElements = document.querySelectorAll(".info-inner")
//   const origOffsetY = Array.from(headerFixedElements).map((headerFixed) => {
//     return headerFixed.offsetTop
//   })

//   headerFixedHolder.addEventListener("scroll", () => {
//     const scrollTop = headerFixedHolder.scrollTop;
//     headerFixedElements.forEach((headerFixed, idx) => {
//       headerFixed.style.top = `${origOffsetY[idx] - scrollTop}px`
//     })
//   })
// }, 2000)})