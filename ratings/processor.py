import sys
import logging
from ratings import elo
from database import db_tools as db


class RatingProcessor:

    def __init__(self, player_dict_dict, rank_file, contest_site):
        self.player_dict_dict = player_dict_dict
        handle_rank_dict = self.read_contest_ranks(rank_file)
        srn_rank_dict = self.create_srn_rank_dict(handle_rank_dict, contest_site)
        self.N, self.Cf, self.Rb_Vb_list = self.get_contest_details(srn_rank_dict)
        self.process_competition(srn_rank_dict)
        self.decay_ratings(srn_rank_dict)

    @staticmethod
    def read_contest_ranks(file_path):
        handle_rank_dict = dict()

        with open(file_path, 'r') as f:
            rank = 1
            for handle in f:
                handle_rank_dict[handle] = rank
                rank += 1
        try:
            assert len(handle_rank_dict) == rank
        except AssertionError:
            logging.error('Duplicate handles provided in ' + file_path)

        return handle_rank_dict

    def create_srn_rank_dict(self, handle_rank_dict, contest_site):

        handle_srn_dict = dict()
        for player_srn in self.player_dict_dict:
            if contest_site in self.player_dict_dict[player_srn]:
                handle = self.player_dict_dict[player_srn][contest_site]
                handle_srn_dict[handle] = player_srn

        unassigned_handles = set(handle_rank_dict.keys()) - set(handle_srn_dict.keys())
        if unassigned_handles:
            logging.error('Following handles are provided in rank list but not mapped to any player:\n{0}'.format(
                str(unassigned_handles)))

        srn_rank_dict = dict()

        for handle in handle_rank_dict:  # Joining the 2 dictionaries
            srn = handle_srn_dict[handle]
            rank = handle_rank_dict[handle]
            srn_rank_dict[srn] = rank

        return srn_rank_dict

    def get_contest_details(self, srn_rank_dict):
        rating_list = []
        vol_list = []

        for srn in srn_rank_dict:
            rating = self.player_dict_dict[srn][db.RATING]
            volatility = self.player_dict_dict[srn][db.VOLATILITY]
            rating_list.append(rating)
            vol_list.append(volatility)

        n = len(srn_rank_dict)
        competition_factor = elo.Cf(rating_list, vol_list, n)
        rating_vol_tup_list = list(zip(rating_list, vol_list))

        return n, competition_factor, rating_vol_tup_list

    def _process_player(self, player_dict, actual_rank):
        """
        :param player_dict: dictionary containing player's details
        :param actual_rank: rank of the player in the competition
        :return: dictionary of player's details after processing rank
        """

        old_rating = player_dict[db.RATING]
        old_volatility = player_dict[db.VOLATILITY]
        times_played = player_dict[db.TIMES_PLAYED]
        old_best = player_dict[db.BEST]

        new_rating, new_volatility = elo.process(
            old_rating, old_volatility, times_played, actual_rank, self.Rb_Vb_list, self.N, self.Cf)

        player_dict[db.RATING] = new_rating
        player_dict[db.VOLATILITY] = new_volatility
        player_dict[db.TIMES_PLAYED] = times_played + 1
        player_dict[db.BEST] = max(old_best, new_rating)
        player_dict[db.LAST_FIVE] = 5

        return player_dict

    def process_competition(self, srn_rank_dict):
        for player_srn in srn_rank_dict:
            actual_rank = srn_rank_dict[player_srn]
            player_dict = self.player_dict_dict[player_srn]
            player_dict = self._process_player(player_dict, actual_rank)
            self.player_dict_dict[player_srn] = player_dict

        logging.info('Successfully processed competition')

    def decay_ratings(self, srn_rank_dict):
        """
        Reduces ratings by 10% for those who have competed at least once
        but have not taken part in the past 5 contests
        :param srn_rank_dict:
        :return:
        """
        for player_srn in self.player_dict_dict:
            if player_srn not in srn_rank_dict:
                rating = self.player_dict_dict[player_srn][db.RATING]
                times_played = self.player_dict_dict[player_srn][db.TIMES_PLAYED]
                last_five = self.player_dict_dict[player_srn][db.LAST_FIVE]-1

                if last_five == 0 and times_played > 0:
                    rating = rating*0.9
                    last_five = 5

                self.player_dict_dict[player_srn][db.RATING] = rating
                self.player_dict_dict[player_srn][db.LAST_FIVE] = last_five

        logging.info('Successfully decayed ratings')


def read_argv(argv_format_alert):
    """
    :param argv_format_alert: An error message on what the command line arguments should be
    :return: 2-tuple of rank file and the contest site if argv is valid
    """
    try:
        assert len(sys.argv) == 3
        rank_file = sys.argv[1]
        contest_site = sys.argv[2]
        try:
            open(rank_file)
            return rank_file, contest_site
        except IOError:
            logging.error('Invalid file path for rank file\n' + argv_format_alert)

    except AssertionError:
        logging.error('Invalid command line arguments.\n' + argv_format_alert)


if __name__ == "__main__":
    argv_format = 'processor.py rank_file_path contest_site_str'
    rank_file_path, contest_site_str = read_argv(argv_format)
    old_db = db.read_database()
    rp = RatingProcessor(old_db, rank_file_path, contest_site_str)
    new_db = rp.player_dict_dict
    db.write_database(new_db)
    logging.info('Ratings processed successfully')
