function generate_elections_table(elections) {
    "use strict";

    var body = document.getElementsByTagName("body")[0];

    var tbl = document.createElement("table");
    var tblBody = document.createElement("tbody");

    var row = document.createElement("tr");
    add_cell("Election", row);
    add_cell("Type", row);
    add_cell("Jurisdiction", row);
    add_cell("Date", row);
    tblBody.appendChild(row);

    for (var i = 0; i < elections.length; i++) {
        row = document.createElement("tr");
        add_cell(elections[i]["Election"], row);
        add_cell(elections[i]["Type"], row);
        add_cell(elections[i]["Jurisdiction"], row);
        add_cell(elections[i]["Date"], row);
        tblBody.appendChild(row);
    }

    tbl.appendChild(tblBody);
    body.appendChild(tbl);
}

function generate_election(elections) {
    "use strict";
    generate_elections_table(elections);
}

function add_cell(text, row) {
    "use strict";

    var cell = document.createElement("td");
    var cell_link = document.createElement("a");
    cell_link.innerHTML = text;
    cell_link.setAttribute("onclick", "test()");
    cell.appendChild(cell_link);
    row.appendChild(cell);
}

function test() {
    console.log("success");
}
