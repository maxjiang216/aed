function set_state_fill(state_id, color) {
    // sets state to color
    // state_id is two letter abbr
    // color is rgb
    "use strict";
    
    var x = document.getElementsByClassName("state");
    for (var i = 0; i < x.length; i++) {
        if (x[i].id == state_id) {
            x[i].style.fill = color;
            return;
        }
    }
    
}

function get_state_color(state) {
    "use strict";
    
    var x = document.getElementsByClassName("state");
    for (var i = 0; i < x.length; i++) {
        if (x[i].id == state) {
            return x[i].style.fill;
        }
    }
    
}

function get_election(election_type) {
    "use strict";
    // retrieve election year, view type
    // from HTML
    // passes value to map colorer
    
    var select = document.getElementById("election-year");
    var election_year = select.options[select.selectedIndex].value;
    
    select = document.getElementById("view-type");
    var view_type = select.options[select.selectedIndex].value;
    color_states(get_election_data(election_type, election_year),
                 view_type,
                 2); // use default rule of 1 for now
    
}

function color_states(data, view_type, rule) {
    "use strict";
    // colors states in accordance to specified rule
    // uses data

    var colors = {};
    var nat_env = {}
    for (var key in data) {
        if (key != '_COLORS') {
            for (var party in data[key]) {
                if (!(party in nat_env)) { // first occurrence of party
                    nat_env[party] = data[key][party];
                }
                else {
                    nat_env[party] += data[key][party];
                }
            }
        }
    }
    for (var key in data) { // get colors
        if (key != '_COLORS') {
            colors[key] = get_color_from_margin(data[key],
                                                data['_COLORS'],
                                                view_type,
                                                nat_env,
                                                rule);
        }
    }
    var states = document.getElementsByClassName("state");
    for (var i = 0; i < states.length; i++) { // save all objects to their state
        if (states[i].id in colors) { // color proper color if in dictionary
            states[i].style.fill = colors[states[i].id]
        }
        else {
            states[i].style.fill = "rgb(107, 110, 115)";
        }
    }

}

function get_color_from_margin(data, legend, view_type, nat_env, rule) {

    if (view_type == "result") {
        // Find first place party
        var currmax = 0;
        var maxname = "";
        for (var party in data) {
            if (party != 'Total' && data[party] > currmax) {
                currmax = data[party];
                maxname = party;
            }
        }
        // Find second place party
        var currsec = 0;
        var secname = "";
        for (var party in data) {
            if (party != 'Total' && party != maxname && data[party] > currsec) {
                currsec = data[party];
                secname = party;
            }
        }
        // color of winning party
        var color = legend[maxname];
        // compute MOV
        var margin = (currmax - currsec)/data['Total'];
    }
    else if (view_type == "bias") { // compute national environment
        var color = legend['Republican']; // Republican by default, assume no ties
        var margin = (data['Republican']-data['Democratic'])/data['Total'];
        margin -= (nat_env['Republican'] - nat_env['Democratic'])/nat_env['Total'];
        if (margin < 0) {
            color = legend['Democratic'];
            margin *= -1;
        }
    }

    // Rule 0: 4 colors from YAPMS
    // Tossup: 0
    // Tilt: (0,2)
    // Lean: [2,5)
    // Likely: [5,10)
    // Solid: [10,100)
    if (rule == 0) {
        if (margin == 0) { // tossup
            return "rgb(107, 110, 115)";
        }
        else if (color == "Red") { // red party; Republican
            if (margin >= 0.1) { // solid
                return "rgb(191,29,41)";
            }
            else if (margin >= 0.05) { // Likely
                return "rgb(255,88,101)";
            }
            else if (margin >= 0.02) { // Lean
                return "rgb(255,139,152)";
            }
            else if (margin > 0) { // Tilt
                return "rgb(207,137,128)";
            }
        }
        else if (color == "Blue") { // blue party; Democratic
            if (margin >= 0.1) { // Solid
                return "rgb(28,64,140)";
            }
            else if (margin >= 0.05) { // Likely
                return "rgb(87,124,204)";
            }
            else if (margin >= 0.02) { // Lean
                return "rgb(138,175,255)";
            }
            else if (margin > 0) { // Tilt
                return "rgb(148,155,179)";
            }
        }
        else if (color == "Yellow") {
            if (margin >= 0.1) { // Solid
                return "rgb(230,183,0)";
            }
            else if (margin >= 0.05) { // Likely
                return "rgb(232,200,77)";
            }
            else if (margin >= 0.02) { // Lean
                return "rgb(255,231,138)";
            }
            else if (margin > 0) { // Tilt
                return "rgb(184,162,82)";
            }
        }
        else if (color == "Green") {
            if (margin >= 0.1) { // Solid
                return "rgb(28,140,40)";
            }
            else if (margin >= 0.05) { // Likely
                return "rgb(80,200,94)";
            }
            else if (margin >= 0.02) { // Lean
                return "rgb(138,255,151)";
            }
            else if (margin > 0) { // Tilt
                return "rgb(122,153,126)";
            }
        }
        else if (color == "Purple") {
            if (margin >= 0.1) { // Solid
                return "rgb(110,46,91)";
            }
            else if (margin >= 0.05) { // Likely
                return "rgb(171,106,153)";
            }
            else if (margin >= 0.02) { // Lean
                return "rgb(197,157,204)";
            }
            else if (margin > 0) { // Tilt
                return "rgb(178,146,154)";
            }
        }
    }

    // Rule 1: 4 color gradient scaled linearly
    // Tilt: 0+
    // Lean: 2+
    // Likely: 5+
    // Solid: 10+
    // weighted average based on distance
    if (rule == 1) {
        if (color == "Red") { // REP
            return linear_gradient(margin,
                                   [[207,137,128],[255,139,152],[255,88,101],[191,29,41]],
                                   [0.02,0.05,0.1]);
        }
        else if (color == "Blue") { // DEM
            return linear_gradient(margin,
                                   [[148,155,179],[138,175,255],[87,124,204],[28,64,140]],
                                   [0.02,0.05,0.1]);
        }
        else if (color == "Yellow") {
            return linear_gradient(margin,
                                   [[184,162,82],[255,231,138],[232,200,77],[230,183,0]],
                                   [0.02,0.05,0.1]);
        }
        else if (color == "Green") {
            return linear_gradient(margin,
                                   [[122,153,126],[138,255,151],[80,200,94],[28,140,40]],
                                   [0.02,0.05,0.1]);
        }
        else if (color == "Purple") {
            return linear_gradient(margin,
                                   [[178,146,154],[187,157,204],[171,106,153],[110,46,91]],
                                   [0.02,0.05,0.1]);
        }
    }

    // Rule 2: 4 color gradient scaled linearly (wider)
    // Tilt: 0+
    // Lean: 5+
    // Likely: 10+
    // Solid: 20+
    // weighted average based on distance
    if (rule == 2) {
        if (color == "Red") { // RE
            return linear_gradient(margin,
                                   [[207,137,128],[255,139,152],[255,88,101],[191,29,41]],
                                   [0.05,0.1,0.2]);
        }
        else if (color == "Blue") { // DEM
            return linear_gradient(margin,
                                   [[148,155,179],[138,175,255],[87,124,204],[28,64,140]],
                                   [0.05,0.1,0.2]);
        }
        else if (color == "Yellow") {
            return linear_gradient(margin,
                                   [[184,162,82],[255,231,138],[232,200,77],[230,183,0]],
                                   [0.05,0.1,0.2]);
        }
        else if (color == "Green") {
            return linear_gradient(margin,
                                   [[122,153,126],[138,255,151],[80,200,94],[28,140,40]],
                                   [0.05,0.1,0.2]);
        }
        else if (color == "Purple") {
            return linear_gradient(margin,
                                   [[178,146,154],[187,157,204],[171,106,153],[110,46,91]],
                                   [0.05,0.1,0.2]);
        }
    }

    // Rule 3: 4 color gradient scaled linearly, start with white
    // Tilt: 0+
    // Lean: 2+
    // Likely: 5+
    // Solid: 10+
    // weighted average based on distance
    if (rule == 3) {
        if (margin >= 0.1) { // Solid REP
            var r = (1-margin)/0.9*255+(margin-0.1)/0.9*191,
                g = (1-margin)/0.9*88+(margin-0.1)/0.9*29,
                b = (1-margin)/0.9*101+(margin-0.1)/0.9*41;
            return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
        }
        else if (margin >= 0.05) { // Likely REP
            var r = (0.1-margin)/0.05*255+(margin-0.05)/0.05*255,
                g = (0.1-margin)/0.05*139+(margin-0.05)/0.05*88,
                b = (0.1-margin)/0.05*152+(margin-0.05)/0.05*101;
            return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
        }
        else if (margin >= 0.02) { // Lean REP
            var r = (0.05-margin)/0.03*207+(margin-0.02)/0.03*255,
                g = (0.05-margin)/0.03*137+(margin-0.02)/0.03*139,
                b = (0.05-margin)/0.03*128+(margin-0.02)/0.03*152;
            return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
        }
        else if (margin > 0) { // Tilt REP
            var r = (0.02-margin)/0.02*255+margin/0.02*207,
                g = (0.02-margin)/0.02*255+margin/0.02*137,
                b = (0.02-margin)/0.02*255+margin/0.02*128;
            return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
        }
        else if (margin <= -0.1) { // Solid DEM
            var r = (margin+1)/0.9*87+(-0.1-margin)/0.9*28,
                g = (margin+1)/0.9*124+(-0.1-margin)/0.9*64,
                b = (margin+1)/0.9*204+(-0.1-margin)/0.9*140;
            return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
        }
        else if (margin <= -0.05) { // Likely DEM
            var r = (margin+0.1)/0.05*138+(-0.05-margin)/0.05*87,
                g = (margin+0.1)/0.05*175+(-0.05-margin)/0.05*124,
                b = (margin+0.1)/0.05*255+(-0.05-margin)/0.05*204;
            return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
        }
        else if (margin <= -0.02) { // Lean DEM
            var r = (margin+0.05)/0.03*148+(-0.02-margin)/0.03*138,
                g = (margin+0.05)/0.03*155+(-0.02-margin)/0.03*175,
                b = (margin+0.05)/0.03*179+(-0.02-margin)/0.03*255;
            return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
        }
        else if (margin < 0) { // Tilt DEM
            var r = (margin+0.02)/0.02*255-margin/0.02*148,
                g = (margin+0.02)/0.02*255-margin/0.02*155,
                b = (margin+0.02)/0.02*255-margin/0.02*179;
            return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
        }
        else { // Tossup
            return "rgb(255, 255, 255)";
        }
    }

}

function linear_gradient(point, colors, cutoffs) {
    // There should be N colors
    // and N-1 cutoffs between 0 and 1
    // if percentage point is in [cutoffs[i-1],cutoffs[i]) for i < N-1
    // cutoffs[-1]=0
    // Then the "weighted average" of colors[i] and colors[i+1] is returned
    // in the form rbg(xxx, xxx, xxx)
    // if point <= 0 then rgb(107, 110, 115) is returned
    if (point <= 0) {
        return "rgb(107, 110, 115)";
    }
    else if (point >= cutoffs[cutoffs.length-1]) {
        var r = colors[colors.length-1][0],
            g = colors[colors.length-1][1],
            b = colors[colors.length-1][2];
        return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
    }
    else if (point < cutoffs[0]) {
        var r = ((cutoffs[0]-point)*colors[0][0]+point*colors[1][0])/cutoffs[0],
            g = ((cutoffs[0]-point)*colors[0][1]+point*colors[1][1])/cutoffs[0],
            b = ((cutoffs[0]-point)*colors[0][2]+point*colors[1][2])/cutoffs[0];
        return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
    }
    else {
        for (var i = 0; i < cutoffs.length-1; i++) {
            if (point >= cutoffs[i] && point < cutoffs[i+1]) {
                var d = cutoffs[i+1] - cutoffs[i];
                var r = ((cutoffs[i+1]-point)*colors[i+1][0]+(point-cutoffs[i])*colors[i+2][0])/d,
                    g = ((cutoffs[i+1]-point)*colors[i+1][1]+(point-cutoffs[i])*colors[i+2][1])/d,
                    b = ((cutoffs[i+1]-point)*colors[i+1][2]+(point-cutoffs[i])*colors[i+2][2])/d;
                return "rgb("+r.toString()+","+g.toString()+","+b.toString()+")";
            }
        }
    }
    return "rgb(107, 110, 115)";

}


function get_election_data(election_type, election_year) {
    "use strict";
    if (typeof AED_ELECTIONS === "undefined" || !AED_ELECTIONS) {
        return {};
    }
    var slice = AED_ELECTIONS[election_type];
    if (!slice) {
        return {};
    }
    return slice[election_year] || {};
}

