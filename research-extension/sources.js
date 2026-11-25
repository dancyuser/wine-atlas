'use strict';
const SOURCES = [
 ['Wine Enthusiast','https://www.wineenthusiast.com/wine-ratings/'],
 ['Wine Spectator','https://top100.winespectator.com/archives/'],
 ['Decanter','https://www.decanter.com/wine-reviews/search/'],
 ['Decanter World Wine Awards','https://www.decanter.com/decanter-world-wine-awards/top-20-value-golds-best-wines-under-15-from-dwwa-2024-531852/'],
 ['James Suckling','https://www.jamessuckling.com/wine-tasting-reports/great-value-wines-7-riojas-for-under-20'],
 ['Robert Parker Wine Advocate','https://content.robertparker.com/best-wines-2019-mark-squires'],
 ['Falstaff','https://www.falstaff.com/at/weine'],
 ['Tim Atkin','https://timatkin.com/score-ranges/90-95/'],
 ['Jancis Robinson','https://www.jancisrobinson.com/articles/grattamacco-2022-bolgheri-rosso'],
 ['Luca Maroni','https://www.lucamaroni.it/vini/371015-san-marzano-primitivo-puglia-igp-2023'],
 ['Vinous','https://vinous.com/'],
 ['Wine & Spirits','https://www.wineandspiritsmagazine.com/the-short-list/great-rioja-for-under-25'],
 ['IWSC','https://www.iwsc.net/news/wine/results-revealed-iwsc-judging-in-conegliano-valdobbiadene'],
 ['Concours Mondial de Bruxelles','https://results.concoursmondial.com/fr/resultats/2024'],
 ['BOTTI','https://www.botti.no/smaksnotater-bestillingsutvalget-mai-2024-rode-viner/'],
 ["Ken's Wine Guide",'https://www.kenswineguide.com/wine.php?page=0'],
 ['Винлаб','https://www.winelab.ru/catalog/vino'],
 ['Ароматный мир','https://amwine.ru/catalog/vino/'],
 ['Vinissimo','https://vinissimo.biz/catalog/wine/'],
 ['Sabonis','https://sabonis.ru/catalog/vino'],
 ['WineStyle','https://spb.winestyle.ru/wine/'],
 ['SimpleWine','https://simplewine.ru/catalog/vino/filter/main-to-5000/'],
 ['AST.WINE','https://ast.wine/catalog/vino/'],
 ['Joia','https://joia.ru/'],
 ['Luding','https://spb.luding.ru/collection/wine/']
];
const RETAILERS = new Set(['Винлаб','Ароматный мир','Vinissimo','Sabonis','WineStyle','SimpleWine','AST.WINE','Joia','Luding']);
const RECHECK = [
 ['Wine Enthusiast','https://www.wineenthusiast.com/buying-guide/bodegas-ramon-bilbao-2022-crianza-tempranillo-rioja/'],
 ['Falstaff','https://www.falstaff.com/nordics/wines/inama-2023-foscarino-soave-classico-doc-1'],
 ['Vinous','https://vinous.com/wines/inama-soave-classico-foscarino/2023'],
 ["Ken's Wine Guide",'https://www.kenswineguide.com/wine_review/Beronia-2023-Tempranillo'],
 ['SimpleWine','https://simplewine.ru/catalog/vino/filter/rating_num-from-90-to-95/','rated'],
 ['Sabonis','https://sabonis.ru/productDetail/vino-ramon-bilbao-kriansa-doc-riokha-10'],
 ['Vinissimo','https://vinissimo.biz/catalog/wine/foscarino_soave_classico_doc_inama-1367923/']
];
if(typeof module!=='undefined') module.exports={SOURCES};
