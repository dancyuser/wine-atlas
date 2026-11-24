'use strict';
const SOURCES = [
 ['Wine Enthusiast','https://www.wineenthusiast.com/wine-ratings/'],
 ['Wine Spectator','https://www.winespectator.com/'],
 ['Decanter','https://www.decanter.com/wine-reviews/search/'],
 ['Decanter World Wine Awards','https://results.decanter.com/'],
 ['James Suckling','https://www.jamessuckling.com/'],
 ['Robert Parker Wine Advocate','https://www.robertparker.com/'],
 ['Falstaff','https://www.falstaff.com/at/weine'],
 ['Tim Atkin','https://timatkin.com/'],
 ['Jancis Robinson','https://www.jancisrobinson.com/'],
 ['Luca Maroni','https://www.lucamaroni.it/'],
 ['Vinous','https://vinous.com/'],
 ['Wine & Spirits','https://www.wineandspiritsmagazine.com/'],
 ['IWSC','https://iwsc.net/results/search'],
 ['Concours Mondial de Bruxelles','https://results.concoursmondial.com/en/results'],
 ["Ken's Wine Guide",'https://www.kenswineguide.com/'],
 ['Винлаб','https://www.winelab.ru/catalog/vino'],
 ['Ароматный мир','https://amwine.ru/catalog/vino/'],
 ['Vinissimo','https://vinissimo.biz/catalog/wine/'],
 ['Sabonis','https://sabonis.ru/catalog/vino'],
 ['WineStyle','https://spb.winestyle.ru/wine/'],
 ['SimpleWine','https://simplewine.ru/catalog/vino/'],
 ['AST.WINE','https://ast.wine/catalog/vino/'],
 ['Joia','https://joia.ru/'],
 ['Luding','https://spb.luding.ru/collection/wine/']
];
const RETAILERS = new Set(['Винлаб','Ароматный мир','Vinissimo','Sabonis','WineStyle','SimpleWine','AST.WINE','Joia','Luding']);
const RECHECK = [
 ['Wine Enthusiast','https://www.wineenthusiast.com/buying-guide/bodegas-ramon-bilbao-2022-crianza-tempranillo-rioja/'],
 ['Falstaff','https://www.falstaff.com/nordics/wines/inama-2023-foscarino-soave-classico-doc-1'],
 ['Vinous','https://vinous.com/wines/inama-2023-soave-classico-foscarino'],
 ['Sabonis','https://sabonis.ru/productDetail/vino-ramon-bilbao-kriansa-doc-riokha-10'],
 ['Vinissimo','https://vinissimo.biz/catalog/wine/foscarino_soave_classico_doc_inama-1367923/']
];
if(typeof module!=='undefined') module.exports={SOURCES};
