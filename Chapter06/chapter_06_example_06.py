"""
TODO how to stats artists
"""
import argparse
import collections
import copy
import os
import random
import shutil
import timeit
from itertools import cycle
from multiprocessing import Manager
from multiprocessing.pool import Pool
from typing import List, Optional

import matplotlib.pyplot as plt
import tables
from pretty_midi import PrettyMIDI, program_to_instrument_name, Instrument

from lakh_utils import get_msd_score_matches, get_midi_path, \
  get_matched_midi_md5
from lakh_utils import msd_id_to_h5
from threading_utils import Counter

parser = argparse.ArgumentParser()
parser.add_argument("--sample_size", type=int, default=1000)
parser.add_argument("--path_dataset_dir", type=str, required=True)
parser.add_argument("--path_match_scores_file", type=str, required=True)
parser.add_argument("--path_output_dir", type=str, required=True)
args = parser.parse_args()

MSD_SCORE_MATCHES = get_msd_score_matches(args.path_match_scores_file)


def extract_pianos(msd_id: str) -> List[PrettyMIDI]:
  os.makedirs(args.path_output_dir, exist_ok=True)
  midi_md5 = get_matched_midi_md5(msd_id, MSD_SCORE_MATCHES)
  midi_path = get_midi_path(msd_id, midi_md5, "matched", args.path_dataset_dir)
  pm = PrettyMIDI(midi_path)
  pm.instruments = [instrument for instrument in pm.instruments
                    if instrument.program == 0 and not instrument.is_drum]
  pm_pianos = []
  if len(pm.instruments) > 1:
    for piano_instrument in pm.instruments:
      pm_piano = copy.deepcopy(pm)
      pm_piano_instrument = Instrument(program=0)
      pm_piano.instruments = [pm_piano_instrument]
      for note in piano_instrument.notes:
        pm_piano_instrument.notes.append(note)
      pm_pianos.append(pm_piano)
  else:
    pm_pianos.append(pm)
  for index, pm_piano in enumerate(pm_pianos):
    if len(pm_piano.instruments) != 1:
      raise Exception(f"Invalid number of piano {msd_id}: "
                      f"{len(pm_piano.instruments)}")
    if pm_piano.get_end_time() > 2000:
      raise Exception(f"Piano track too long {msd_id}: "
                      f"{pm_piano.get_end_time()}")
    pm_piano.write(os.path.join(args.path_output_dir, f"{msd_id}_{index}.mid"))
  return pm_pianos


def process(msd_id: str, counter: Counter) -> Optional[dict]:
  try:
    with tables.open_file(msd_id_to_h5(msd_id, args.path_dataset_dir)) as h5:
      pm_pianos = extract_pianos(msd_id)
      return {"msd_id": msd_id, "pm_pianos": pm_pianos}
  except Exception as e:
    print(f"Exception during processing of {msd_id}: {e}")
    return
  finally:
    counter.increment()

def app(msd_ids: List[str]):
  start = timeit.default_timer()

  # TODO cleanup
  shutil.rmtree(args.path_output_dir, ignore_errors=True)

  # TODO info
  with Pool(4) as pool:
    manager = Manager()
    counter = Counter(manager, len(msd_ids))
    print("START")
    results = pool.starmap(process, zip(msd_ids, cycle([counter])))
    results = [result for result in results if result]
    print("END")
    results_percentage = len(results) / len(msd_ids) * 100
    print(f"Number of tracks: {len(MSD_SCORE_MATCHES)}, "
          f"number of tracks in sample: {len(msd_ids)}, "
          f"number of results: {len(results)} "
          f"({results_percentage}%)")

  # TODO histogram
  pm_pianos_list = [result["pm_pianos"] for result in results]
  pm_piano_lengths = [pm_piano.get_end_time()
                      for pm_pianos in pm_pianos_list
                      for pm_piano in pm_pianos]
  plt.hist(pm_piano_lengths, bins=100)
  plt.ylabel('length (sec)')
  plt.title('Piano lengths')
  plt.show()

  stop = timeit.default_timer()
  print("Time: ", stop - start)


if __name__ == "__main__":
  if args.sample_size:
    # Process a sample of it
    MSD_IDS = random.sample(list(MSD_SCORE_MATCHES), args.sample_size)
  else:
    # Process all the dataset
    MSD_IDS = list(MSD_SCORE_MATCHES)
  app(MSD_IDS)