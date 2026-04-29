function generateTable(data) {
    "use strict";
    // get body
    var body = document.getElementsByTagName("body")[0];
    // create table
    var tbl = document.createElement("table");
    var tblBody = document.createElement("tbody");
    // add cells
    for (var i = 0; i < Object.keys(data).length; i++) {
        var row = document.createElement("tr");
        console.log(data[Object.keys(data)[i]]);
        var region = document.createElement("td");
        var regionName = document.createTextNode(Object.keys(data)[i]);
        region.appendChild(regionName);
        row.appendChild(region);
        for (var j = 0; j < Object.keys(data[Object.keys(data)[i]]).length; j++) {
            var cell = document.createElement("td");
            var cellText = document.createTextNode(Object.values(data[Object.keys(data)[i]])[j]);
            cell.appendChild(cellText);
            row.appendChild(cell);
        }
        tblBody.appendChild(row);
    }
    tbl.appendChild(tblBody);
    body.appendChild(tbl);
}

var elections = []; // list of elections with results
elections.push({"Election":"2020 Presidential Election","Jurisdiction":"Federal","Type":"Presidential","Date":"02/11/2020","Winner":"Joe Biden (D)","Results":{"Alabama":{"Joe Biden (D)":849624,"Donald Trump (R)":1441170,"Total":2323282},"Alaska":{"Joe Biden (D)":153778,"Donald Trump (R)":189951,"Total":359530},"Arizona":{"Joe Biden (D)":1672143,"Donald Trump (R)":1661686,"Total":3387326},"Arkansas":{"Joe Biden (D)":423932,"Donald Trump (R)":760647,"Total":1219069},"California":{"Joe Biden (D)":11110250,"Donald Trump (R)":6006429,"Total":17500871},"Colorado":{"Joe Biden (D)":1804352,"Donald Trump (R)":1364607,"Total":3256980},"Connecticut":{"Joe Biden (D)":1080680,"Donald Trump (R)":715291,"Total":1824273},"Delaware":{"Joe Biden (D)":296268,"Donald Trump (R)":200603,"Total":504346},"District of Columbia":{"Joe Biden (D)":317323,"Donald Trump (R)":18586,"Total":344356},"Florida":{"Joe Biden (D)":5297045,"Donald Trump (R)":5668731,"Total":11067456},"Georgia":{"Joe Biden (D)":2473633,"Donald Trump (R)":2461854,"Total":4997716},"Hawaii":{"Joe Biden (D)":366130,"Donald Trump (R)":196864,"Total":574469},"Idaho":{"Joe Biden (D)":287021,"Donald Trump (R)":554119,"Total":867884},"Illinois":{"Joe Biden (D)":3471915,"Donald Trump (R)":2446891,"Total":6033744},"Indiana":{"Joe Biden (D)":1242413,"Donald Trump (R)":1729516,"Total":3033112},"Iowa":{"Joe Biden (D)":759061,"Donald Trump (R)":897672,"Total":1690871},"Kansas":{"Joe Biden (D)":570323,"Donald Trump (R)":771406,"Total":1372303},"Kentucky":{"Joe Biden (D)":772474,"Donald Trump (R)":1326646,"Total":2136768},"Louisiana":{"Joe Biden (D)":856034,"Donald Trump (R)":1255776,"Total":2148062},"Maine":{"Joe Biden (D)":435072,"Donald Trump (R)":360737,"Total":819461},"Maryland":{"Joe Biden (D)":1985023,"Donald Trump (R)":976414,"Total":3037030},"Massachusetts":{"Joe Biden (D)":2382202,"Donald Trump (R)":1167202,"Total":3631402},"Michigan":{"Joe Biden (D)":2804040,"Donald Trump (R)":2649852,"Total":5539302},"Minnesota":{"Joe Biden (D)":1717077,"Donald Trump (R)":1484065,"Total":3277171},"Mississippi":{"Joe Biden (D)":539508,"Donald Trump (R)":756789,"Total":1313894},"Missouri":{"Joe Biden (D)":1253014,"Donald Trump (R)":1718736,"Total":3025962},"Montana":{"Joe Biden (D)":244786,"Donald Trump (R)":343602,"Total":603674},"Nebraska":{"Joe Biden (D)":374583,"Donald Trump (R)":556846,"Total":956383},"Nevada":{"Joe Biden (D)":703486,"Donald Trump (R)":669890,"Total":1405376},"New Hampshire":{"Joe Biden (D)":424921,"Donald Trump (R)":365654,"Total":806182},"New Jersey":{"Joe Biden (D)":2608335,"Donald Trump (R)":1883274,"Total":4549353},"New Mexico":{"Joe Biden (D)":501614,"Donald Trump (R)":401894,"Total":923965},"New York":{"Joe Biden (D)":5230985,"Donald Trump (R)":3244798,"Total":8594826},"North Carolina":{"Joe Biden (D)":2684292,"Donald Trump (R)":2758775,"Total":5524804},"North Dakota":{"Joe Biden (D)":114902,"Donald Trump (R)":235595,"Total":361819},"Ohio":{"Joe Biden (D)":2679165,"Donald Trump (R)":3154834,"Total":5922202},"Oklahoma":{"Joe Biden (D)":503890,"Donald Trump (R)":1020280,"Total":1560699},"Oregon":{"Joe Biden (D)":1340383,"Donald Trump (R)":958448,"Total":2374321},"Pennsylvania":{"Joe Biden (D)":3458229,"Donald Trump (R)":3377674,"Total":6915283},"Rhode Island":{"Joe Biden (D)":307486,"Donald Trump (R)":199922,"Total":517757},"South Carolina":{"Joe Biden (D)":1091541,"Donald Trump (R)":1385103,"Total":2513329},"South Dakota":{"Joe Biden (D)":150471,"Donald Trump (R)":261043,"Total":422609},"Tennessee":{"Joe Biden (D)":1143711,"Donald Trump (R)":1852475,"Total":3053851},"Texas":{"Joe Biden (D)":5259126,"Donald Trump (R)":5890347,"Total":11315056},"Utah":{"Joe Biden (D)":560282,"Donald Trump (R)":865140,"Total":1488289},"Vermont":{"Joe Biden (D)":242820,"Donald Trump (R)":112704,"Total":367428},"Virginia":{"Joe Biden (D)":2413568,"Donald Trump (R)":1962430,"Total":4460524},"Washington":{"Joe Biden (D)":2369612,"Donald Trump (R)":1584651,"Total":4087631},"West Virginia":{"Joe Biden (D)":235984,"Donald Trump (R)":545382,"Total":794731},"Wisconsin":{"Joe Biden (D)":1630866,"Donald Trump (R)":1610184,"Total":3298041},"Wyoming":{"Joe Biden (D)":73491,"Donald Trump (R)":193559,"Total":276765}}})