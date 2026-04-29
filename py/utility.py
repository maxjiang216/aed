def get_state_abbr(string, state=False):
    '''Returns two-letter state abbreviation'''

    if not state: # no change
        return string
    d = {'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'districtofcolumbia': 'DC', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD', 'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'newhampshire': 'NH', 'newjersey': 'NJ', 'newmexico': 'NM', 'newyork': 'NY', 'northcarolina': 'NC', 'northdakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhodeisland': 'RI', 'southcarolina': 'SC', 'southdakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'westvirginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY'}
    out = d.get(''.join(string.split()).lower())
    if out == None:
        return string
    return out

def get_county_name(county, state):
    '''Returns county name used in Mapchart labels'''

    county = county.upper()
    state_abbr = get_state_abbr(state)
    if county == "BEDFORD" and state_abbr == "VA":
        return "BEDFORD_CO___VA"
    elif county == "CHARLES CITY" and state_abbr == "VA":
        return "CHARLES_CITY__VA"
    elif county == "JAMES CITY" and state_abbr == "VA":
        return "JAMES_CITY__VA"
    elif county == "ST. LOUIS" and state_abbr == "MO":
        return "ST__LOUIS_CO___MO"
    elif county == "STE. GENEVIEVE" and state_abbr == "MO":
        return "SAINTE_GENEVIEVE__MO"
    elif county == "DE KALB" and state_abbr == "MO":
        return "DEKALB__MO"
    elif county == "LASALLE" and state_abbr == "IL":
        return "LA_SALLE__IL"
    elif county == "DEWITT" and state_abbr == "IL":
        return "DE_WITT__IL"
    elif county == "ST. MARY'S" and state_abbr == "MD":
        return "ST_MARY_S__MD"
    elif county == "BALTIMORE CITY" and state_abbr == "MD":
        return "BALTIMORE_CITY__MD"
    elif county in ["BALTIMORE COUNTY","BALTIMORE"] and state_abbr == "MD":
        return "BALTIMORE_COUNTY__MD"
    elif county == "SAINT LOUIS" and state_abbr == "MN":
        return "ST__LOUIS__MN"
    elif county == "LA SALLE" and state_abbr == "LA":
        return "LASALLE__LA"
    elif county == "FAIRFAX" and state_abbr == "VA":
        return "ROANOKE_CO___VA"
    elif county == "CARSON CITY" and state_abbr == "NV":
        return "CARSON_CITY__NV"
    else:
        if county[-5:] == " CITY":
            county = county[:-5] # remove final "city"
        county = county.replace("COUNTY","CO.") # Mapchart uses Co
        county = county.replace('Ñ', 'N')
        county = county.replace('Ö', 'O')
        county = county.replace('.', '_')
        county = county.replace('\'', '_')
        county = county.replace('-', '_')
        county = county.replace(' ', '_')
        return county.upper() + '__' + state_abbr

def replace_county(file, state):
    out = ""
    for line in open(file+".txt",'r',encoding='utf8'):
        lst = line.split('\t')
        lst[0] = get_county_name(lst[0],state)
        out += '\t'.join(lst)
    open(file+'.txt','w').write(out)

def get_party_lst(lst):
    out = []
    for i in lst:
        out.append(get_party_abbr(i))
    return out

def get_party_abbr(string):
    '''Returns proper name of party given abbreviation/variation'''

    abbrs = {
        "Democratic":{"dem","democrat","democratic","democraticparty"}
    }

    for abbr in abbrs:
        if ''.join(string.split()).lower() in abbrs[abbr]:
            return abbr
    return string # if not found

def recolor_svg_hex(file_name, color, recolor):
    '''Scales coordinates in SVG path object'''
    outfile = open(file_name+'_recolor.txt','w')
    for line in open(file_name+'.txt','r'):
        if "<path " not in line or " fill=\"#"+color+"\"" not in line:
            outfile.write(line)
            continue
        prefix = line[:line.find(" fill=\"#")+8]
        coord = line[line.find(" fill=\"#")+8:]
        suffix = coord[coord.find('"'):]
        coord = coord[:coord.find('"')]
        outfile.write(prefix+recolor+suffix)
    outfile.close()

def add_class(file, class_name):

    out = ""
    for line in open(file+'.txt','r'):
        lst = line.strip().split(' ')
        for i in range(len(lst)-1,-1,-1):
            if "class=\"" in lst[i]:
                lst.pop(i)
        lst.insert(1,"class=\""+class_name+"\"")
        out += ' '.join(lst) + '\n'
    open(file+'.txt','w').write(out)

def change_id_case(file, upper=True):

    out = ""
    for line in open(file+'.txt','r'):
        lst = line.strip().split(' ')
        for i in range(len(lst)):
            if "id=\"" in lst[i]:
                if upper:
                    lst[i] = "id=\"" + lst[i].split('"')[1].upper() + '"'
                else:
                    lst[i] = "id=\"" + lst[i].split('"')[1].upper() + '"'
                break
        out += ' '.join(lst) + '\n'

    open(file+'_case.txt','w').write(out)

def replace_map(html, map, n = 4):
    '''replace map in html with contents in map (svg)'''
    out = ""
    flag = False
    flag2 = False
    done = False
    for line in open(html+'.html','r'):
        if flag2:
            if "<path " not in line:
                flag2 = False
                flag = False
                out += line
            elif not done:
                for part in open(map + ".txt", 'r'):
                    out += ' ' * n + part.strip() + '\n'
                done = True
        elif flag:
            if "<path " in line:
                flag2 = True
            else:
                out += line
        else:
            out += line
            if "<svg " in line:
                flag = True

    open(html+".html",'w').write(out)

def change_all_case(file, upper=True):
    '''changes everything in file to upper case is upper=True and lowercase otherwise'''
    out = ""
    for line in open(file+'.txt','r'):
        out += line.upper()
    open(file+'.txt','w').write(out)

def get_MIT_county(file, target):

    first = True
    years = {}
    for line in open(file,'r'):
        if first:
            first = False
            continue
        lst = line.split(',')
        if lst[8] == "NA":
            continue
        year = int(lst[0])

        name = ""
        if lst[4] == "\"51059\"":
            name = "FAIRFAX_CO___VA"
        elif lst[4] == "\"51067\"":
            name = "FRANKLIN_CO___VA"
        elif lst[4] == "\"51159\"":
            name = "RICHMOND_CO___VA"
        elif lst[4] == "\"51161\"":
            name = "ROANOKE_CO___VA"
        else:
            name = get_county_name(lst[3][1:-1], lst[2][1:-1])

        party = lst[7][1:-1]
        votes = int(lst[8])

        if year not in years:
            years[year] = {}
        if name not in years[year]:
            years[year][name] = [0,0,0] # D, R, T
        if party == "DEMOCRAT":
            years[year][name][0] += votes
        elif party == "REPUBLICAN":
            years[year][name][1] += votes
        years[year][name][2] += votes

    for year in years:
        outfile = open(target+"/"+str(year)+".txt",'w')
        outfile.write("_PARTIES\tDemocrat\tRepublican\tTotal\n")
        outfile.write("_COLORS\tBlue\tRed\n")
        for county in years[year]:
            outfile.write("{0}\t{1}\t{2}\t{3}\n".format(county,years[year][county][0],
                                                        years[year][county][1],years[year][county][2]))
        outfile.close()

get_MIT_county("../MIT/countypres_2000-2020.csv","../elections/US_president_county")
