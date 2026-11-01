/**
 * Applies the saved theme before first paint, so a viewer who chose light on a
 * dark OS does not get a flash of the wrong palette.
 */
export function ThemeScript() {
  const js = `(function(){try{var m=localStorage.getItem("ti-theme");if(m==="light"||m==="dark"){document.documentElement.setAttribute("data-theme",m);}}catch(e){}})();`;
  return <script dangerouslySetInnerHTML={{ __html: js }} />;
}
