#!/usr/bin/env python
# Copyright 2016 The xi-editor Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Utility for distilling Unicode data into properties which can be
# efficiently queried.

# Usage: python tools/mk_tables.py datadir > src/tables.rs
# datadir should point to Unicode data, including LineBreak.txt

import os
import sys
import random

linebreak_assignments = ['XX', 'AI', 'AL', 'B2', 'BA', 'BB', 'BK', 'CB', 'CL',
'CM', 'CR', 'EX', 'GL', 'HY', 'ID', 'IN', 'IS', 'LF', 'NS', 'NU', 'OP', 'PO',
'PR', 'QU', 'SA', 'SG', 'SP', 'SY', 'ZW', 'NL', 'WJ', 'H2', 'H3', 'JL', 'JT',
'JV', 'CP', 'CJ', 'HL', 'RI', 'EB', 'EM', 'ZWJ']

inv_lb_assigments = dict((val, i) for (i, val) in enumerate(linebreak_assignments))

def gen_data(data, width=80):
    line = ''
    for val in data:
        new = '%d,' % val
        if len(line) + 1 + len(new) > width :
            print(line)
            line = ''
        prefix = ' ' if line else '    '
        line += prefix + new
    print(line)

def gen_table(name, t, data, width=80):
    print('\n#[rustfmt::skip]')
    print('pub const %s: [%s; %d] = [' % (name, t, len(data)))
    gen_data(data)
    print('];')

def compute_trie(rawdata, chunksize):
    root = []
    childmap = {}
    child_data = []
    for i in range(int(len(rawdata) / chunksize)):
        data = rawdata[i * chunksize: (i + 1) * chunksize]
        child = '|'.join(map(str, data))
        if child not in childmap:
            childmap[child] = len(childmap)
            child_data.extend(data)
        root.append(childmap[child])
    return (root, child_data)

def compute_trie2(rawdata, midsize, leafsize):
    (mid, leaves) = compute_trie(rawdata, leafsize)
    (root, midnodes) = compute_trie(mid, midsize)
    return (root, midnodes, leaves)

def load_unicode_props(datadir, fn):
    f = open(os.path.join(datadir, fn))

    lb = ['XX'] * 0x110000;
    did_notice = False

    for line in f:
        if line.startswith('#'):
            if not did_notice:
                orig = line.split('#', 1)[1].strip()
                print("// This file autogenerated from %s by mk_tables.py" % orig)
                did_notice = True
        s = line.split(' ')[0].split(';')
        if len(s) == 2:
            t = s[0].split('..')
            lo = int(t[0], 16)
            hi = int(t[-1], 16) + 1
            for cp in range(lo, hi):
                lb[cp] = s[1]

    numeric_lb = [inv_lb_assigments[lb[cp]] for cp in range(0x110000)]
    return numeric_lb

def mk_linebreak_props(datadir):
    numeric_lb = load_unicode_props(datadir, 'LineBreak.txt')

    # generate table for 1 and 2 byte utf-8, direct lookup
    gen_table('LINEBREAK_1_2', 'u8', numeric_lb[0:0x800])

    (root3, child3) = compute_trie(numeric_lb[0x800:0x10000], 0x40)
    gen_table('LINEBREAK_3_ROOT', 'u8', [255] * 32 + root3);
    gen_table('LINEBREAK_3_CHILD', 'u8', child3);

    (root4, mid4, leaves4) = compute_trie2(numeric_lb[0x10000:], 0x40, 0x40)
    gen_table('LINEBREAK_4_ROOT', 'u8', [255] * 16 + root4);
    gen_table('LINEBREAK_4_MID', 'u8', mid4);
    gen_table('LINEBREAK_4_LEAVES', 'u8', leaves4);

def mk_tables(datadir):
    print("""// Copyright 2016 The xi-editor Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Raw trie data for linebreak property lookup.
""")
    mk_linebreak_props(datadir)
    mk_lb_rules()

def mk_tests(datadir, do_str = False):
    numeric_lb = load_unicode_props(datadir, 'LineBreak.txt')
    ranges = (range(0x80), range(0x80, 0x800), range(0x800, 0x10000), range(0x10000, 0x110000))
    for r in ranges:
        for cp in sorted(random.sample(r, 32)):
            if 0xD800 <= cp and cp < 0xE000: continue  # invalid codepoint
            lb_prop = numeric_lb[cp]
            if do_str:
                if cp < 0x80:
                    cplen = 1
                elif cp < 0x800:
                    cplen = 2
                elif cp < 0x10000:
                    cplen = 3
                else:
                    cplen = 4
                print('        assert_eq!((%d, %d), linebreak_property_str(&"\\u{%04X}", 0));' % (lb_prop, cplen, cp))
            else:
                print('        assert_eq!(%2d, linebreak_property(\'\\u{%04X}\'));' % (lb_prop, cp))

def update(table, left, right, new):
    if type(left) == str: left = [left]
    if type(right) == str: right = [right]
    for l in left:
        for r in right:
            key = l + '|' + r
            if key not in table: table[key] = new

def update_both(table1, table2, left, right, new):
    update(table1, left, right, new)
    update(table2, left, right, new)

def resolve_ambig(orig):
    # LB1
    if orig in ('AI', 'SG', 'XX'):
        return 'AL'
    elif orig in 'SA':
        # TODO: need to incorporate this into property lookup
        return 'AL'
    elif orig == 'CJ':
        return 'NS'
    else:
        return orig

def mk_lb_rules():
    # Rules derived from UAX #14

    t = {}
    ts = {}  # transitions for when there is one or more SP
    Any = linebreak_assignments + ['HL+HY', 'HL+BA', 'RI+RI']
    # LB1: todo (affects South East Asian scripts)

    # LB2: handled in code
    # LB3: handled in code

    # LB4
    update(t, 'BK', Any, '!')

    # LB5
    update(t, 'CR', 'LF', 'x')
    update(t, 'CR', Any, '!')
    update(t, 'LF', Any, '!')
    update(t, 'NL', Any, '!')

    # LB6
    update_both(t, ts, Any, ['BK', 'CR', 'LF', 'NL'], 'x')

    # LB7
    update_both(t, ts, Any, ['SP'], 'x')
    update_both(t, ts, Any, ['ZW'], 'x')

    # LB8
    update_both(t, ts, 'ZW', Any, '_')

    # LB8a
    update(t, 'ZWJ', ['ID', 'EB', 'EM'], 'x')

    # LB9: handled in state machine construction
    # LB10: handled in state machine construction

    # LB11:
    update_both(t, ts, Any, 'WJ', 'x')
    update(t, 'WJ', Any, 'x')

    # LB12:
    update(t, 'GL', Any, 'x')

    # LB12:
    excl = set(linebreak_assignments) - set(('SP', 'BA', 'HY'))
    update(t, excl, 'GL', 'x')

    # LB13:
    update_both(t, ts, Any, 'CL', 'x')
    update_both(t, ts, Any, 'CP', 'x')
    update_both(t, ts, Any, 'EX', 'x')
    update_both(t, ts, Any, 'IS', 'x')
    update_both(t, ts, Any, 'SY', 'x')

    # LB14
    update_both(t, ts, 'OP', Any, 'x')

    # LB15
    update_both(t, ts, 'QU', 'OP', 'x')

    # LB16
    update_both(t, ts, ['CL', 'CP'], 'NS', 'x')

    # LB17
    update_both(t, ts, 'B2', 'B2', 'x')

    # LB18
    update(t, 'SP', Any, '_')
    update(ts, Any, Any, '_')  # note deviation from literal transcription

    # LB19
    update_both(t, ts, Any, 'QU', 'x')
    update(t, 'QU', Any, 'x')

    # LB20
    update_both(t, ts, Any, 'CB', '_')
    update(t, 'CB', Any, '_')

    # LB21
    update_both(t, ts, Any, 'BA', 'x')
    update_both(t, ts, Any, 'HY', 'x')
    update_both(t, ts, Any, 'NS', 'x')
    update(t, 'BB', Any, 'x')

    # LB21a: special states reached in state machine
    update(t, ['HL+HY', 'HL+BA'], Any, 'x')

    # LB21b:
    update(t, 'SY', 'HL', 'x')

    # LB22:
    update(t, ['AL', 'HL'], 'IN', 'x')
    update(t, 'EX', 'IN', 'x')
    update(t, ['ID', 'EB', 'EM'], 'IN', 'x')
    update(t, 'IN', 'IN', 'x')
    update(t, 'NU', 'IN', 'x')

    # LB23:
    update(t, ['AL', 'HL'], 'NU', 'x')
    update(t, 'NU', ['AL', 'HL'], 'x')

    # LB23a:
    update(t, 'PR', ['ID', 'EB', 'EM'], 'x')
    update(t, ['ID', 'EB', 'EM'], 'PO', 'x')

    # LB24:
    update(t, 'PR', ['AL', 'HL'], 'x')
    update(t, 'PO', ['AL', 'HL'], 'x')
    update(t, 'AL', ['PR', 'PO'], 'x')
    update(t, 'HL', ['PR', 'PO'], 'x')

    # LB25:
    update(t, 'CL', 'PO', 'x')
    update(t, 'CP', 'PO', 'x')
    update(t, 'CL', 'PP', 'x')
    update(t, 'CP', 'PR', 'x')
    update(t, 'NU', 'PO', 'x')
    update(t, 'NU', 'PR', 'x')
    update(t, 'PO', 'OP', 'x')
    update(t, 'PO', 'NU', 'x')
    update(t, 'PR', 'OP', 'x')
    update(t, 'PR', 'NU', 'x')
    update(t, 'HY', 'NU', 'x')
    update(t, 'IS', 'NU', 'x')
    update(t, 'NU', 'NU', 'x')
    update(t, 'SY', 'NU', 'x')

    # LB26:
    update(t, 'JL', ['JL', 'JV', 'H2', 'H3'], 'x')
    update(t, ['JV', 'H2'], ['JV', 'JT'], 'x')
    update(t, ['JT', 'H3'], 'JT', 'x')

    # LB27:
    update(t, ['JL', 'JV', 'JT', 'H2', 'H3'], 'IN', 'x')
    update(t, ['JL', 'JV', 'JT', 'H2', 'H3'], 'PO', 'x')
    update(t, 'PR', ['JL', 'JV', 'JT', 'H2', 'H3'], 'x')

    # LB28:
    update(t, ['AL', 'HL'], ['AL', 'HL'], 'x')

    # LB29:
    update(t, 'IS', ['AL', 'HL'], 'x')

    # LB30:
    update(t, ['AL', 'HL', 'NU'], 'OP', 'x')
    update(t, 'CP', ['AL', 'HL', 'NU'], 'x')

    # LB30a:
    update(t, 'RI', 'RI', 'x')
    update(t, Any, 'RI+RI', '_')
    update(t, 'RI+RI', Any, '_')

    # LB30b:
    update(t, 'EB', 'EM', 'x')

    # LB31:
    update_both(t, ts, Any, Any, '_')

    # state machine construction
    # states [0..43) correspond to LB class of previous ch
    # state 43 is 'HL+HY'
    # state 44 is 'HL+BA'
    # state 45 is 'RI+RI'
    # states [46..89) correspond to LB class (SP+)
    # result is new state on bottom (LB of right ch), + 0x80 if break + 0x40 if hard
    # (note that only states 0..43 need be represented if break)
    n = len(linebreak_assignments)
    nspecial = 3
    nstates = n * 2 + nspecial
    sm = []
    for i in range(nstates):
        sm.append([-1] * n)
    bk_to_flags = {'x': 0, '_': 0x80, '!': 0xc0}
    for left in range(n + nspecial):
        L = Any[left]
        if L == 'CM':
            L = 'AL'  # handling for LB10
        L = resolve_ambig(L)
        for right in range(n):
            R = linebreak_assignments[right]
            R = resolve_ambig(R)
            r_with_cm = right
            l_with_cm = left
            if R in ['CM', 'ZWJ'] and L in ['BK', 'CR', 'LF', 'NL', 'SP', 'ZW']:
                # handling for LB10
                r_with_cm = 2  # AL
                bk = t[L + '|' + 'AL']
            elif L == 'ZWJ' and R not in ['ID', 'EB', 'EM']:
                #handling for LB10
                l_with_cm = 2  # AL
                bk = t['AL' + '|' + R]
            else:
                bk = t[L + '|' + R]
            flags = bk_to_flags[bk]
            if flags == 0 and R == 'SP':
                if left < n:
                    state = left + n + nspecial
                else:
                    state = left
            elif flags == 0 and L == 'HL' and R == 'HY':
                # special state for LB21a
                state = n
            elif flags == 0 and L == 'HL' and R == 'BA':
                # special state for LB21a
                state = n + 1
            elif R in ['CM', 'ZWJ'] and L not in ['BK', 'CR', 'LF', 'NL', 'SP', 'ZW']:
                # handling for LB9
                state = l_with_cm
            elif flags == 0 and R == 'RI' and L == 'RI':
                # handling for LB31
                state = n + 2
            else:
                state = flags + r_with_cm
            #print('//', L, R, bk, state
            sm[left][right] = state

            if left < n:
                # SP+ states
                bk = ts[L + '|' + R]
                flags = bk_to_flags[bk]
                sm[left + n + nspecial][right] = flags + r_with_cm
    nunique = len(set(str(line) for line in sm))
    print('//', nunique, 'unique states')
    print('pub const N_LINEBREAK_CATEGORIES: usize = %d;' % n)
    print('\n#[rustfmt::skip]')
    print('pub const LINEBREAK_STATE_MACHINE: [u8; %d] = [' % (nstates * n))
    # TODO: dedup
    for state in range(nstates):
        if state < n + nspecial:
            statename = Any[state]
        else:
            statename = 'SP+ ' + Any[state - (n + nspecial)]
        print('    // state %d: %s' % (state, statename))
        gen_data(sm[state])
    print('];')

def main():
    datadir = sys.argv[1]
    if len(sys.argv) == 3 and sys.argv[2] == '--tests':
        return mk_tests(datadir)
    if len(sys.argv) == 3 and sys.argv[2] == '--tests-str':
        return mk_tests(datadir, True)
    else:
        mk_tables(datadir)

main()
