import os
from utility import get_state_abbr, get_party_lst

def update_all(path="../elections"):
    '''Compiles a folder of folders
    Update .html files, .js files'''

    map_js_string(str(compile_all()))

def compile_all(path="../elections"):
    '''Compiles a folder of folders
    folder elections should be a folder of folders (US_president_state, etc.)'''

    out = {}
    for folder in os.listdir(path):
        out[folder] = compile_folder(path + '/' + folder, folder[:3]=="US_")
    return out

def compile_folder(path, state=False):
    '''Compiles all files in folder path
    Updates .html file'''

    out = {}
    years = []
    for filename in os.listdir(path):
        if filename.endswith(".txt"): # only consider .txt files (for safety)
            out[filename.split('.')[0]] = parse(path+'/'+filename, state)
            years.append(filename.split('.')[0])
    update_html("../"+path.split('/')[-1]+".html", years)
    return out

def parse(filename, state=False):
    '''Given a file, parses to return dictionary that can be used by JS to describe a map'''

    results = {} # dictionary mapping subdivision to results (by party)
    parties = [] # ordered list of parties (incl. total)
    colors = [] # ordered list of colors (corresponding to parties, total should be last and not colored)
    for line in open(filename,'r'):
        lst = line.strip().split('\t')
        if lst[0] == "_PARTIES":
            parties = get_party_lst(lst[1:])
        elif lst[0] == "_COLORS":
            colors = lst[1:]
        else:
            results[lst[0]] = lst[1:]
    out = {}
    color_dict = {}
    for i in range(len(colors)):
        color_dict[parties[i]] = colors[i]
    for div in results:
        temp = {}
        sum = 0
        for i in range(len(parties)):
            if i >= len(results[div]):
                if i == len(parties)-1: # total
                    temp[parties[i]] = sum
                else: # third party
                    temp[parties[i]] = 0
            else:
                if results[div][i] == '': # default is 0
                    temp[parties[i]] = 0
                else:
                    temp[parties[i]] = int(results[div][i])
                    sum += int(results[div][i])
        out[get_state_abbr(div, state)] = temp
    out["_COLORS"] = color_dict
    return out

def map_js_string(data, path="../js/map.js"):
    s = ""
    for line in open(path,'r'):
        if "var elections = " in line:
            s += "\tvar elections = {0}\n".format(str(data))
        else:
            s += line
    open(path,'w').write(s)

def update_html(path, years):
    years.sort(reverse=True)
    flag = False
    s = ""
    for line in open(path,'r'):
        if "<div class=\"wrapper\"><select name=\"election-year\" id=\"election-year\"" in line:
            flag = True
            s += line
            for year in years:
                s += "\t\t<option value=\"{0}\">{0}</option>\n".format(year)
        if "</select>" in line:
            flag = False
        if not flag:
            s += line
    open(path,'w').write(s)

update_all()