import enum
import pprint
import tempfile
from typing import Dict, Optional

from gspg import config
from gspg.core.github import clone_repo, calc_lines_local_repo


class RetCode(enum.Enum):
    OK = 0
    IS_FORK = 1
    IS_EMPTY = 2


def collect_data(user_name: str, token: str):
    gen = collect_data_gen(user_name, token)
    while True:
        processed, left, stats = next(gen)
        if left == 0:
            return stats


def collect_data_gen(user_name: str, token: str):
    if token.startswith('github'):
        from gspg.core.github import get_repos
    else:
        yield 0, 0, None
        # from gspg.core.gitlab import get_repo_langs, get_repos

    repos = get_repos(token)

    if config.DEBUG:
        print(f'Total {len(repos)} repos')

    if len(repos) == 0:
        yield 0, 0, None

    lang_stats = dict()
    processed_count = 0

    left_count = min(len(repos), config.MAX_REPOS_TO_PROCESS if config.DEBUG else len(repos))

    for repo in repos:
        yield processed_count, left_count, lang_stats

        ret_code, cur_repo_lang_stats = _process_repo(repo, user_name, token)
        if ret_code == RetCode.OK and cur_repo_lang_stats is not None:
            # add current values to general statistics
            for lang, lang_info in cur_repo_lang_stats.items():
                if lang not in lang_stats:
                    lang_stats[lang] = dict()

                for param, count in lang_info.items():
                    if param not in lang_stats[lang]:
                        lang_stats[lang][param] = count
                    else:
                        lang_stats[lang][param] += count

        processed_count += 1
        left_count -= 1

    yield processed_count, left_count, lang_stats


def _process_repo(repo: Dict, user_name: str, token: str) -> (RetCode, Optional[Dict]):
    permissions = repo['permissions']
    if permissions['admin'] is True:
        permission_str = 'admin'
    elif permissions['maintain'] is True:
        permission_str = 'admin'
    else:
        permission_str = 'other'

    is_fork = repo['fork']
    fork_info_str = 'fork' if is_fork else 'own'

    if config.DEBUG:
        print(f"{repo['name']} ({'private' if repo['private'] else 'public'}, {permission_str}, {fork_info_str}): "
              f"{repo['language']}")

    if is_fork:
        return RetCode.IS_FORK, None

    if repo['language'] is None:
        return RetCode.IS_EMPTY, None

    lang_stats = dict()

    # main
    cur_repo_lang_stats = _calc_main(user_name, token, repo)
    bytes_mapping = {
        'C': 'C/C++',
        'C++': 'C/C++',
    }
    for lang, code_bytes in cur_repo_lang_stats.items():
        if lang in bytes_mapping:
            lang = bytes_mapping[lang]

        if lang is None:
            continue

        if lang not in lang_stats:
            lang_stats[lang] = dict()

        if 'bytes' not in lang_stats[lang]:
            lang_stats[lang]['bytes'] = 0

        lang_stats[lang]['bytes'] += code_bytes

    # lines
    lines_stats = _calc_repo_lines(user_name, repo['name'])
    lines_mapping = {
        'Bourne Shell': 'Shell',
        'Bourne Again Shell': 'Shell',
        'DOS Batch': 'Batchfile',
        'make': 'Makefile',
        'Vuejs Component': 'Vue',
        'C': 'C/C++',
        'C++': 'C/C++',
        'C/C++ Header': 'C/C++',
        'JSON': None
    }
    for lang, lines in lines_stats.items():
        if lang in lines_mapping:
            lang = lines_mapping[lang]

        if lang is None:
            continue

        if lang not in lang_stats:
            lang_stats[lang] = dict()

        if 'lines' not in lang_stats[lang]:
            lang_stats[lang]['lines'] = 0

        lang_stats[lang]['lines'] += lines

    return RetCode.OK, lang_stats


def _calc_main(user_name: str, token: str, repo: Dict) -> Dict:
    if token.startswith('github'):
        from gspg.core.github import get_repo_langs
    else:
        # from gspg.core.gitlab import get_repo_langs
        return dict()

    repo_langs = get_repo_langs(user_name, token, repo['name'])
    if config.DEBUG:
        pprint.pprint(repo_langs)

    if len(repo_langs) == 0:
        return dict()

    lang_stats = dict()
    for lang, code_bytes in repo_langs.items():
        if lang in lang_stats:
            lang_stats[lang] += int(code_bytes)
        else:
            lang_stats[lang] = code_bytes

    return lang_stats


def _calc_repo_lines(user_name: str, repo_name: str) -> Dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_dir = clone_repo(user_name, repo_name, tmp_dir)
        if repo_dir:
            return calc_lines_local_repo(repo_dir)

    return dict()
