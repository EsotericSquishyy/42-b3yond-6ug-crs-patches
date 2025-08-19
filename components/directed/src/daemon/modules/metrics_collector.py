import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class MetricsCollector:
    def __init__(self):
        """Initialize the MetricsCollector for AFL++ fuzzer stats."""
        self.required_metrics = [
            'run_time', 'execs_done', 'execs_per_sec', 'corpus_count', 
            'corpus_favored', 'corpus_found', 'bitmap_cvg', 'saved_crashes',
            'saved_hangs', 'last_find', 'last_crash', 'edges_found', 'total_edges',
            'execs_ps_last_min', 'cycles_done', 'pending_favs', 'pending_total',
            'stability', 'var_byte_count'
        ]

    def parse_stats_file(self, stats_file: Path) -> Dict[str, Any]:
        """
        Parse AFL++ fuzzer_stats file and extract relevant metrics.
        
        Args:
            stats_file (Path): Path to the fuzzer_stats file
            
        Returns:
            Dict[str, Any]: Dictionary containing the parsed metrics
        """
        try:
            if not stats_file.exists():
                logger.error(f"Stats file not found: {stats_file}")
                return {}

            metrics = {}
            with open(stats_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or ':' not in line:
                        continue
                        
                    key, value = [x.strip() for x in line.split(':', 1)]
                    if key in self.required_metrics:
                        try:
                            # Convert numeric values
                            if '%' in value:
                                metrics[key] = float(value.rstrip('%'))
                            elif '.' in value:
                                metrics[key] = float(value)
                            else:
                                metrics[key] = int(value)
                        except ValueError:
                            metrics[key] = value

            # Calculate additional metrics
            if 'edges_found' in metrics and 'total_edges' in metrics:
                metrics['edge_coverage'] = (metrics['edges_found'] / metrics['total_edges']) * 100

            return metrics

        except Exception as e:
            logger.error(f"Error parsing stats file {stats_file}: {e}")
            return {}

    def collect_metrics(self, fuzzer_dir: Path) -> Dict[str, Any]:
        """
        Collect metrics from a fuzzer instance directory.
        
        Args:
            fuzzer_dir (Path): Path to the fuzzer instance directory
            
        Returns:
            Dict[str, Any]: Dictionary containing all collected metrics
        """
        stats_file = fuzzer_dir / 'fuzzer_stats'
        return self.parse_stats_file(stats_file) 