"""permapfiller module.
An extension of pandas DataFrames to fill incomplete performance maps.
"""

import warnings

import pandas as pd

from .defaults import build_default_corrections


@pd.api.extensions.register_dataframe_accessor('pmf')
class PermapFiller:
    """
    Complete missing values in a performance map.

    PermapFiller objects are accessible through the DataFrame accessor
    `pmf`.  They provide a handful of methods to help extend an
    initially incomplete performance map, given as a DataFrame.

    Parameters
    ----------
    pandas_obj : DataFrame
        The pandas dataframe representing the performance map.

    Attributes
    ----------
    mode : {'heating', 'cooling'}, default None
        The operating mode associated with the performance data.
    normalized : bool, default False.
        ``True`` if the performance data is normalized.  It is
        automatically set to ``True`` after using the `normalize` method.
    entries : dict, default {'freq': [0.2, 0.5, 1], 'AFR': [0, 1]}
        Entries for the missing quantities in the performance map.
        Particular entries can be set using
        ``self.entries[quantity] = list_of_entries``
    corrections : dict, default None
        Two-level nested dictionary  with single variable corrections
        used to extend the performance map.  A different correction
        should be provided for each input and output quantity.  The keys
        of the first level are the input quantities and those of the
        second level are the output quantities.  Dictionary values
        (the corrections) must be provided as functions with one
        argument. See examples for more details.
    manval_factors : dict, default None
        Manufacturer tables are not always provided in rated conditions;
        for example, some performance tables are provided at maximum
        compressor frequency and not at the rated frequency value.  For
        each input quantity not present in the initial performance map,
        this attributes gives the ratio between the value associated
        with the inital data and the rated value.  If none have been
        set, the default dict {'freq': 1, 'AFR': 1} is assigned when the
        operating mode is set.

    Examples
    --------
    Build an incomplete performance map and
    set (missing) normalized frequency entries:

    >>> initial_map = fmo.build_heating_permap()
    >>> heat_map = initial_map.pmf.set_entries('freq', np.arange(1, 21)/10)

    If performances are not given at rated frequency, a correction
    factor must be set.  Assuming performances are given at maximum
    frequency (120 Hz) and rated frequency is 60 Hz, the frequency
    correction ratio should be

    >>> heat_map.pmf.manval_factors['freq'] = 120 / 60

    There are no corrections by default until the operating mode is set:

    >>> heat_map.pmf.corrections is None
    True
    >>> heat_map.pmf.mode = 'heating'
    >>> corr = heat_map.pmf.corrections['freq']['power']
    >>> corr(0.5)
    0.20785906320354824
    >>> corr(1)
    0.9999997589861805

    """

    _attributes_to_copy = (
        '_mode',
        '_normalized',
        '_entries',
        '_corrections',
        '_manval_factors'
    )

    def __init__(self, pandas_obj):
        """Constructor for the PermapFiller class."""
        self._obj = pandas_obj
        self._mode = None
        self._normalized = False
        self._entries = {'freq': [0.2, 0.5, 1], 'AFR': [0, 1]}
        self._corrections = None
        self._manval_factors = None

    @property
    def mode(self):
        """The operating mode corresponding to the performance data."""
        return self._mode

    @mode.setter
    def mode(self, operating_mode):
        """Setter for the operating mode.

        If either the corrections or the manufacturer values factors are
        None, default values are automatically set together with the
        mode.

        Parameters
        ----------
        operating_mode : {'heating', 'cooling'}
            The operating mode associated with the performance data.

        Warns
        -----
        UserWarning
            If corrections are not None and a new mode is set
            (corrections are not overwritten).

        """
        if 'cool' in operating_mode.lower():
            self._mode = 'cooling'
        elif 'heat' in operating_mode.lower():
            self._mode = 'heating'
        else:
            err_msg = "'value' argument must be either 'heating' or 'cooling'."
            raise ValueError(err_msg)
        self._obj.columns.name = self.mode
        if self.corrections is None:
            self.corrections = build_default_corrections(self.mode)
            self._add_corrections(inplace=True)
        else:
            warnings.warn(
                "Corrections are already set and were not overwritten, though "
                "they may need to be changed after setting a new mode."
            )
        if self.manval_factors is None:
            self.manval_factors = {'freq': 1, 'AFR': 1}
            if self.mode == 'cooling':
                self.manval_factors['Twbr'] = 1

    @property
    def normalized(self):
        return self._normalized

    def copy(self):
        return self.copyattr(self)

    def copyattr(self, other):
        """Return a copy of `self` with some selected attributes copied
        from `other`.
        """
        new = self._obj.copy()
        if isinstance(other, PermapFiller):
            for attribute in PermapFiller._attributes_to_copy:
                setattr(new.pmf, attribute, getattr(other, attribute))
        else:
            if hasattr(other, 'pmf'):
                for attribute in PermapFiller._attributes_to_copy:
                    setattr(new.pmf, attribute, getattr(other.pmf, attribute))
            else:
                first = type(other).__name__[0].lower()
                aan = 'a' if first in ('a', 'e', 'i', 'o', 'u') else 'an'
                raise TypeError(
                    f"argument should be a {type(self).__name__}. "
                    f"You provided {aan} {type(other).__name__}."
                )
        return new

    @property
    def entries(self):
        return self._entries

    @entries.setter
    def entries(self, new_entries):
        # Particular entries can be set using self.entries[quantity] = entries
        #                                             |        |          |
        #                                           dict      str        list
        self._entries = new_entries

    def normalize(self, values=None):
        """Normalize values in the performance map.

        Parameters
        ----------
        values : DataFrame, optional
            A pandas dataframe with one row containing the rated values
            of the performance map output quantities in its columns.
            The performance data will be normalized by those values.  By
            default, `values` is ``None`` and in that case the original
            performance map is returned.

        Returns
        -------
        pm : DataFrame
            A copy of the original performance map with performance
            values normalized according to the rated values, and the
            `normalized` attribute set to ``True``.

        Raises
        ------
        RuntimeError
            If the data is already normalized
            (`self.normalized` is ``True``).
        ValueError
            If there is an inconsistency between the PermapFiller column
            index and the rated values dataframe column index.

        See also
        --------
        PermapFiller.fillmap :
            Fill the missing values and optionally normalize the data
            in one go.

        Examples
        --------
        >>> initial_map = fmo.build_cooling_permap()
        >>> cool_map = initial_map.pmf.set_entries('freq', np.arange(1, 14)/10)
        >>> cool_map.pmf.mode = 'cooling'
        >>> cool_map
        cooling          capacity  power
        Tdbr Twbr Tdbo
        17.8 12.2 -10.0      3.03   0.28
                  -5.0       3.01   0.33
                   0.0       2.98   0.36
                   5.0       2.96   0.39
                   10.0      2.94   0.40
        ...                   ...    ...
        32.2 22.8  25.0      4.44   0.65
                   30.6      4.20   0.73
                   35.0      3.94   0.81
                   40.0      3.33   0.75
                   46.0      3.07   0.75

        [72 rows x 2 columns]

        >>> rated_values = pd.DataFrame({'capacity': [3.52], 'power': [0.79]})
        >>> norm = cool_map.pmf.normalize(rated_values)
        >>> norm
        cooling          capacity     power
        Tdbr Twbr Tdbo
        17.8 12.2 -10.0  0.860795  0.354430
                  -5.0   0.855114  0.417722
                   0.0   0.846591  0.455696
                   5.0   0.840909  0.493671
                   10.0  0.835227  0.506329
        ...                   ...       ...
        32.2 22.8  25.0  1.261364  0.822785
                   30.6  1.193182  0.924051
                   35.0  1.119318  1.025316
                   40.0  0.946023  0.949367
                   46.0  0.872159  0.949367

        [72 rows x 2 columns]

        Trying to normalize again will fail:
        >>> norm.normalize(rated_values)
        Traceback (most recent call last):
        ...
        RuntimeError: values are already normalized.

        """
        if self.normalized:
            raise RuntimeError("values are already normalized.")
        self._check_mode(before='normalizing')
        pm = self.copy()
        if values is None:
            return pm
        pmcols, vacols = set(pm.pmf._obj.columns), set(values.columns)
        mismatch = pmcols ^ vacols
        if mismatch < {'capacity', 'power', 'COP'}:
            if len(pmcols) > len(vacols):
                values = pm.pmf._add_missing_df_column(values)
            elif len(pmcols) < len(vacols):
                pm.pmf._obj = pm.pmf._add_missing_df_column(pm._obj)
            for quantity, value in values.iteritems():
                pm[quantity] /= value[0]
            pm.pmf._normalized = True
            return pm
        else:
            raise ValueError(
                "DataFrame column index must match values column index."
                f"\nIndex are {list(pmcols)}"
                f" and {list(vacols)}"
            )

    @property
    def corrections(self):
        return self._corrections

    @corrections.setter
    def corrections(self, new_corrections):
        self._corrections = new_corrections

    @corrections.deleter
    def corrections(self):
        del self._corrections

    def get_correction(self, input_quantity, output_quantity=None):
        """Retrieve some specific correction functions.

        Parameters
        ----------
        input_quantity : str
            The input of the performance table, wich is the argument of the
            correction function to retrieve.
        output_quantity : str, optional
            The output of the performance table to which the returned
            correction apply.  By default, corrections for all outputs are
            returned in the form of a dictionary.

        Returns
        -------
        callable or dict
            The correction function used to correct the value of the output
            quantity depending on the value of the input quantity, if the
            output quantity is specified.  Otherwise, the correction
            function for each output quantity assembled in a dictionary.

        Raises
        ------
        RuntimeError
            If the operating mode is not yet set.

        See Also
        --------
        PermapFiller.corrections : get all corrections as a dictionary.
        PermapFiller.set_correction :
            Equivalent of `PermapFiller.get_correction` for setting a
            single correction.
        PermapFiller.set_corrections :
            Equivalent of `PermapFiller.get_correction` for setting
            mutliple corrections for a specific input quantity.

        """
        self._check_mode("getting correction")

        if output_quantity is None:
            return self._corrections[input_quantity]
        else:
            return self._corrections[input_quantity][output_quantity]

    def set_correction(
        self,
        input_quantity,
        output_quantity,
        new_correction,
        inplace=False
    ):
        """Set a correction function to adjust the value of a specific
        output quantity depending on a specific input quantity.

        Parameters
        ----------
        input_quantity : str
            The input of the performance table, wich is the argument of the
            correction function to set.
        output_quantity : str
            The output of the performance table to which the correction
            apply.
        new_correction : callable
            The new correction to be set.
        inplace : bool, default ``False``
             If ``True``, performs operation inplace and returns ``None``.


        Returns
        -------
        DataFrame or None
            If `inplace` is ``False``, a copy of the dataframe with the new
            correction is returned.

        Raises
        ------
        RuntimeError
            If the operating mode is not yet set.

        See Also
        --------
        PermapFiller.corrections : get all corrections as a dictionary.
        PermapFiller.get_correction :
            Equivalent of `PermapFiller.set_correction` for getting
            specific corrections.
        PermapFiller.set_corrections :
            Equivalent of `PermapFiller.set_correction` for setting
            multiple corrections for a specific input quantity.

        """
        self._check_mode(before="setting new correction")
        new = None if inplace else self.copy()
        pmf = self if inplace else new.pmf
        updated_corrections = pmf.corrections
        updated_corrections[input_quantity][output_quantity] = new_correction
        pmf.corrections = updated_corrections
        return new

    def set_corrections(self, input_quantity, new_corrections):
        """Set a correction functions to adjust the value of all output
        quantities depending on a specific input quantity.

        Parameters
        ----------
        input_quantity : str
            The input of the performance table, wich is the argument of the
            correction functions to set.
        new_corrections : dict of callables
            The new corrections to be set, with keys corresponding to
            output quantities names.

        Returns
        -------
        DataFrame
            A copy of the dataframe with the new corrections is returned.

        Raises
        ------
        RuntimeError
            If the operating mode is not yet set.

        See Also
        --------
        PermapFiller.corrections : get all corrections as a dictionary.
        PermapFiller.get_correction :
            Equivalent of `PermapFiller.set_corrections` for getting
            specific corrections.
        PermapFiller.set_correction :
            Equivalent of `PermapFiller.set_corrections` for setting a
            single correction.

        """
        self._check_mode(before="setting new corrections")
        new = self.copy()
        updated_corrections = new.pmf.corrections
        updated_corrections[input_quantity] = new_corrections
        new.pmf.corrections = updated_corrections
        return new.pmf._add_correction(input_quantity)

    @property
    def manval_factors(self):
        return self._manval_factors

    @manval_factors.setter
    def manval_factors(self, new_values):
        self._manval_factors = new_values

    @manval_factors.deleter
    def manval_factors(self):
        del self._manval_factors

    def _check_mode(self, before="doing what you did"):
        """Ensure that the mode is set."""
        if self.mode is None:
            error_message = f"attribute 'mode' must be set before {before}."
            raise RuntimeError(error_message)

    def _check_columns(self, keys):
        """Check coherence between column index and a set of keys."""
        columns, keys = set(self._obj.columns), set(keys)
        if columns != keys:
            unmatched_cols = tuple(columns - keys)
            unmatched_keys = tuple(keys - columns)
            error_msg = ["DataFrame column index must match corrections keys."]
            if unmatched_cols != tuple():
                multiple = len(unmatched_cols) > 1
                faulty_cols = unmatched_cols[0] if multiple else unmatched_cols
                error_msg.append(
                    f"DataFrame columns not in correction keys: {faulty_cols}"
                )
            if unmatched_keys != tuple():
                multiple = len(unmatched_cols) > 1
                faulty_keys = unmatched_keys[0] if multiple else unmatched_keys
                error_msg.append(
                    f"Correction keys not in DataFrame columns: {faulty_keys}"
                )
            raise ValueError('\n'.join(error_msg))

    def _check_corrections(self, quantity):
        """Check that the number of corrections makes sense."""
        self._check_mode(before="checking for corrections")
        corrections_number = len(self.corrections[quantity])
        if corrections_number < 2:
            raise ValueError("there should be at least two corrections.")
        elif corrections_number > 3:
            raise ValueError("there are too many (or redundant) corrections.")

    def _add_correction(self, quantity, inplace=False):
        """Add an additional (redundant) correction.

        If a regression on another output quantity (e.g. COP instead of
        capacity) is preferable, this function can automatically add any
        missing correction function that can be deduced from the already
        existing ones.

        Parameters
        ----------
        quantity : str
            The input quantity whose values are used to compute the
            corrections.
        inplace : bool, default ``False``
            If ``True``, performs operation inplace and returns ``None``.

        Returns
        -------
        DataFrame
            A copy of the original dataframe with additional regression(s).

        Raises
        ------
        RuntimeError
            If the operating mode is not yet set.

        See Also
        --------
        PermapFiller._add_corrections :
            Equivalent of `PermapFiller._add_correction` for adding
            regressions for all input quantities.
        PermapFiller.set_correction : set a single correction.
        PermapFiller.set_corrections :
            Set multiple corrections for a specific input quantity.

        """
        self._check_corrections(quantity)
        corrections = self.corrections[quantity]
        all_keys, keys = {'power', 'capacity', 'COP'}, set(corrections.keys())
        if all_keys == keys:
            return self.copy()
        missing_key = (all_keys - keys).pop()
        if missing_key == 'power':
            cap, COP = (corrections[qt] for qt in ('capacity', 'COP'))
            def new_correction(x): return cap(x) / COP(x)
        elif missing_key == 'capacity':
            power, COP = (corrections[qt] for qt in ('power', 'COP'))
            def new_correction(x): return power(x) * COP(x)
        elif missing_key == 'COP':
            power, cap = (corrections[qt] for qt in ('power', 'capacity'))
            def new_correction(x): return cap(x) / power(x)
        else:
            err_msg = "correction key should be 'capacity', 'power' or 'COP'."
            raise ValueError(err_msg)
        if inplace:
            self.set_correction(
                quantity, missing_key, new_correction, inplace=True)
        else:
            return self.set_correction(quantity, missing_key, new_correction)

    def _add_corrections(self, inplace=False):
        """See `PermapFiller._add_correction`."""
        new = None if inplace else self.copy()
        for quantity in set(self.corrections) - {'SHR'}:
            if inplace:
                self._add_correction(quantity, inplace=True)
            else:
                new.pmf = new.pmf._add_correction(quantity)
        if not inplace:
            return new

    @classmethod
    def _add_missing_df_column(cls, df):
        """Add an additional (redundant) output quantity column.

        Parameters
        ----------
        df : DataFrame

        Returns
        -------
        DataFrame
            A copy of the original dataframe with additional column(s).

        """
        _df = df.copy()
        all_columns = {'capacity', 'power', 'COP'}
        columns = set(_df.columns)
        if columns == all_columns:
            return _df
        missing_column = (all_columns - columns).pop()
        if missing_column == 'power':
            missing_values = _df.capacity / _df.COP
        elif missing_column == 'capacity':
            missing_values = _df.power * _df.COP
        elif missing_column == 'COP':
            missing_values = _df.capacity / _df.power
        else:
            err_msg = "column names should be 'capacity', 'power' or 'COP'."
            raise ValueError(err_msg)
        _df[missing_column] = missing_values
        return _df

    def _add_missing_column(self):
        """See classmethod `PermapFiller._add_missing_df_column`."""
        new = self.copy()
        new.pmf._obj = new.pmf._add_missing_df_column(new.pmf._obj)
        return new

    def correct(self, corrections, entry, manval=1):
        """Apply corrections to ouput quantities.

        Parameters
        ----------
        corrections : dict
            A dict with output quantities to adjust as keys, and
            correction functions as values.
        entry : int or float
            Value of the input quantity for which corrections are to
            be applied.
        manval : int or float, default 1
            manufacturer values correction factor
            (see `PermapFiller.manval_factors` in the class documentation).

        Returns
        -------
        DataFrame
            A corrected copy of the original dataframe.

        Raises
        ------
        RuntimeError
            If there is an incoherence between the column index and the
            `corrections` keys (the ouput quantities to be corrected).

        See Also
        --------
        PermapFiller.extend : extend performance map using corrections.
        PermapFiller.fillmap : fill missing values in performance map.

        """
        self._check_columns(corrections.keys())
        new = self.copy()
        for quantity, correction in corrections.items():
            new[quantity] *= correction(entry) / correction(manval)
        return new

    def extend(self, corrections, entries, name='new dim'):
        """Extend the performance map along a new dimension.

        Parameters
        ----------
        corrections : dict
            A dict with output quantities to adjust as keys, and
            correction functions as values.
        entries : iterable of int or float
            Values of the input quantity for which corrections are to
            be applied.
        name : str, default 'new dim'
            Name of the quantity corresponding to the new dimension.

        Returns
        -------
        DataFrame
            An extended copy of the original dataframe.

        Raises
        ------
        RuntimeError
            If there is an incoherence between the column index and the
            `corrections` keys (the ouput quantities to be corrected).

        See Also
        --------
        PermapFiller.correct : apply corrections to ouput quantities.
        PermapFiller.fillmap : fill missing values in performance map.

        """
        self._check_columns(corrections.keys())
        manval = self.manval_factors[name]
        extrusions = [
            self.correct(corrections, entry, manval) for entry in entries
        ]
        new = pd.concat(extrusions, keys=entries, names=[name])
        return new.pmf.copyattr(self)

    def fillmap(self, norm=None):
        """Extend the performance map along a new dimension.

        Parameters
        ----------
        norm : DataFrame, optional
            Pandas dataframe with the rated values used for normalizing the
            data (see `values` argument in the documentation for
            `PermapFiller.normalize` method).  If not provided, the data is
            not normalized.

        Returns
        -------
        DataFrame
            An extended copy of the original dataframe.

        Raises
        ------
        RuntimeError
            If there is an incoherence between the column index and the
            `corrections` keys (the ouput quantities to be corrected).
        RuntimeError
            If the data is already normalized
            (`self.normalized` is ``True``).

        See Also
        --------
        PermapFiller.correct : apply corrections to ouput quantities.
        PermapFiller.extend : extend performance map using corrections.
        PermapFiller.print_permap : write performance map to file.

        Examples
        --------
        Build cooling performance map and set the missing frequency entries

        >>> initial_map = fmo.build_cooling_permap()
        >>> cool_map.pmf.mode = 'cooling'
        >>> cool_map = initial_map.pmf.set_entries('freq', np.arange(1, 14)/10)
        >>> cool_map
        cooling          capacity  power
        Tdbr Twbr Tdbo
        17.8 12.2 -10.0      3.03   0.28
                  -5.0       3.01   0.33
                   0.0       2.98   0.36
                   5.0       2.96   0.39
                   10.0      2.94   0.40
        ...                   ...    ...
        32.2 22.8  25.0      4.44   0.65
                   30.6      4.20   0.73
                   35.0      3.94   0.81
                   40.0      3.33   0.75
                   46.0      3.07   0.75

        [72 rows x 2 columns]

        Fill values for frequency ('freq'), wet-bulb room temperature
        ('Twbr') and air flow rate ('AFR'), and normalize data:

        >>> rated_values = pd.DataFrame({'capacity': [3.52], 'power': [0.79]})
        >>> cool_map.pmf.fillmap(norm=rated_values)
        cooling                      power  sensible_capacity  latent_capacity
        Tdbr Twbr Tdbo  AFR freq
        17.8 12.2 -10.0 0   0.1   0.003268           0.010849         0.013296
                            0.2   0.015247           0.050620         0.062037
                            0.3   0.037015           0.122602         0.150254
                            0.4   0.068330           0.206249         0.252767
                            0.5   0.108010           0.264530         0.324193
        ...                            ...                ...              ...
        32.2 22.8  46.0 1   0.9   0.821848           0.571090         0.206256
                            1.0   0.949367           0.640746         0.231413
                            1.1   1.064119           0.712520         0.257335
                            1.2   1.163336           0.777625         0.280849
                            1.3   1.245864           0.832545         0.300684

        [11232 rows x 3 columns]

        """
        self._check_mode("filling the performance map")
        if norm is not None and self.normalized:
            raise RuntimeError("values are already normalized")

        freq_corr = self.get_correction('freq')
        with_freq = self._add_missing_column().pmf.extend(
            freq_corr, self.entries['freq'], name='freq'
        )
        AFR_corr = self.get_correction('AFR')
        with_AFR = with_freq.pmf.extend(
            AFR_corr, self.entries['AFR'], name='AFR'
        )

        if self.mode == 'heating':
            new_level_order = ['Tdbr', 'Tdbo', 'AFR', 'freq']
            permap = with_AFR.reorder_levels(new_level_order).sort_index()
            permap = permap.pmf.copyattr(self).pmf.normalize(norm)
            permap = permap.reindex(['power', 'capacity'], axis=1)
        elif self.mode == 'cooling':
            without_Twbr = with_AFR.droplevel('Twbr').pmf.copyattr(self)
            Twbr = with_AFR.index.get_level_values('Twbr').unique().to_numpy()
            Twbr_corr = self.get_correction('Twbr')
            with_Twbr = without_Twbr.pmf.extend(Twbr_corr, Twbr, name='Twbr')
            permap = with_Twbr.pmf.normalize(norm)
            Tdb = permap.index.get_level_values('Tdbr').to_numpy()
            Twb = permap.index.get_level_values('Twbr').to_numpy()
            SHR = self.get_correction('SHR')
            permap['sensible_capacity'] = permap.capacity * SHR(Tdb - Twb)
            permap['latent_capacity'] = (
                permap.capacity - permap.sensible_capacity
            )
            permap = permap.drop('capacity', axis='columns')
            new_level_order = ['Tdbr', 'Twbr', 'Tdbo', 'AFR', 'freq']
            permap = permap.reorder_levels(new_level_order).sort_index()
            new_index_order = ['power', 'sensible_capacity', 'latent_capacity']
            permap = permap.reindex(new_index_order, axis='columns')
        else:
            raise ValueError("mode must either be heating or cooling")
        return permap.pmf.copyattr(self)

    def print_permap(self, filename, majororder='row'):
        """Write performance map to a file using a format compatible with
        the TRNSYS Type3254.

        Parameters
        ----------
        filename : str
            The name of the file to be written to.
        majororder : {'row', 'col'}
            Choose to write the performance map either in row- or
            column-major order.

        """
        if not isinstance(majororder, str):
            raise TypeError("order must be either 'row' or 'col'.")
        else:
            order = majororder.lower()
        if order not in ('row', 'col'):
            raise TypeError("order must be either 'row' or 'col'.")

        permap_formatted = pd.concat([self._obj], keys=[''], names=['!#'])
        if order == 'col':
            levels = permap_formatted.index.names
            flip_levels = [levels[0]] + levels[-1:0:-1]
            permap_formatted = permap_formatted.reorder_levels(flip_levels)
        permap_formatted.sort_index().round(10).to_csv(filename, sep='\t')

        def prepend_line(line):
            with open(filename, 'r+') as f:
                content = f.read()
                f.seek(0, 0)
                f.write(line.rstrip('\r\n') + '\n' + content)

        def fetch_index(i):
            index = self._obj.index.get_level_values(i).drop_duplicates()
            return index.name, index.values

        prepend_line("!#\n!# Performance map\n!#")
        nlevels = self._obj.index.nlevels
        for name, values in (fetch_index(i) for i in range(nlevels-1, -1, -1)):
            values_str = '\t'.join(str(v) for v in values)
            s = f"!# {name} values\n   {values_str}\n"
            prepend_line(s.replace('(', '').replace(')', ''))
        for name, values in (fetch_index(i) for i in range(nlevels-1, -1, -1)):
            s = f"!# Number of {name} data points\n   {len(values)}\n"
            prepend_line(s.replace('(', '').replace(')', ''))

        warning = (
            "!# This is a data file for Type 3254. Do not change the format.\n"
            "!# In PARTICULAR, LINES STARTING WITH !# MUST BE LEFT "
            "IN THE FILE AT THEIR LOCATION.\n"
            '!# Comments within "normal lines" (not starting with !#) '
            "are optional but the data must be there.\n"
            "!#\n!# Independent variables\n!#"
        )

        prepend_line(warning)